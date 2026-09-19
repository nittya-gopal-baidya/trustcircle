"""
services/trust_engine.py
------------------------
TrustCircle Standalone Trust Engine Service.

Processes four core signals:
  1. Unique repeat customers (scanned >= 3 times)
  2. Scan-interval consistency (statistical Coefficient of Variation of visit intervals)
  3. Vendor tenure (days since vendor onboarding/creation)
  4. Dispute / chargeback rate (dispute_count / total_transactions)

Architectural Separation:
  - TrustEngine: Pure statistical computation core (independent of database/framework).
  - recalculate_trust(): Async I/O integration layer connecting MongoDB collections.
  - Privacy Gating: K-anonymity enforcement separating internal calculation from customer delivery.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import statistics
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import settings
from app.database import scan_events_col, vendor_stats_col, vendors_col
from app.models.vendor_stats import TrustTier
from app.schemas.vendor import BadgePayload


# =============================================================================
# 1. CONFIGURATION OBJECT: DEMO / HACKATHON SCORING WEIGHTS
# =============================================================================

@dataclass(frozen=True)
class DemoScoringWeights:
    """
    ===========================================================================
    [DEMO / HACKATHON WEIGHTS CONFIGURATION]
    These scoring weights, normalizations, and tier thresholds are heuristic
    parameters designed specifically for hackathon evaluation and transparent
    explainability.

    They do NOT represent Paytm's official, proprietary, or production scoring formula.
    ===========================================================================
    """
    # Numerical weights for the 4 core signals (Sum = 1.0 or 100%)
    REPEAT_CUSTOMER_WEIGHT: float = 0.40   # 40% - Primary social proof signal
    CONSISTENCY_WEIGHT: float = 0.25        # 25% - Habitual regularity of visits
    TENURE_WEIGHT: float = 0.20             # 20% - Merchant operational maturity
    DISPUTE_WEIGHT: float = 0.15            # 15% - Dispute-free transaction record

    # Repeat customer threshold
    REPEAT_SCAN_THRESHOLD: int = 3          # >= 3 scans = repeat customer

    # Tier thresholds based on unique repeat customer count
    TIER_GROWING_MIN: int = 5              # 5-49: GROWING
    TIER_TRUSTED_MIN: int = 50             # 50-499: TRUSTED
    TIER_COMMUNITY_MIN: int = 500          # 500+: COMMUNITY_FAVORITE

    # Privacy & K-Anonymity floor
    K_ANONYMITY_FLOOR: int = 5             # Hide badge if repeat_customers < 5

    # Benchmark scaling limits
    MAX_TENURE_BENCHMARK_DAYS: int = 365   # 365 days = 100/100 tenure score
    MAX_DISPUTE_TOLERANCE_RATE: float = 0.05 # 5% disputes drops dispute score to 0


DEFAULT_CONFIG = DemoScoringWeights()


# =============================================================================
# 2. TIER METADATA & DISPLAY HELPERS
# =============================================================================

TIER_META: dict[TrustTier, dict[str, Optional[str]]] = {
    "NEW": {
        "label": "NO TRUST BADGE",
        "description": "Building history...",
    },
    "GROWING": {
        "label": "GROWING",
        "description": "5+ regulars trust this vendor",
    },
    "TRUSTED": {
        "label": "TRUSTED",
        "description": "50+ regulars trust this vendor",
    },
    "COMMUNITY_FAVORITE": {
        "label": "COMMUNITY FAVORITE",
        "description": "500+ regulars trust this community favorite",
    },
}


def _bucket_scans(total_scans: int) -> str:
    """Privacy-safe bucketing of total scans (e.g. 87 -> '80+')."""
    if total_scans < 10:
        return "a few"
    bucket = (total_scans // 10) * 10
    return f"{bucket}+"


# =============================================================================
# 3. SIGNAL COMPUTATION FUNCTIONS (EXPLAINABLE STATISTICAL APPROACH)
# =============================================================================

def assign_tier(
    repeat_customers: int,
    config: DemoScoringWeights = DEFAULT_CONFIG,
) -> TrustTier:
    """
    Assign vendor trust tier strictly based on unique repeat customer count:
      < 5     -> NEW
      5-49    -> GROWING
      50-499  -> TRUSTED
      500+    -> COMMUNITY_FAVORITE
    """
    if repeat_customers < config.TIER_GROWING_MIN:
        return "NEW"
    elif repeat_customers < config.TIER_TRUSTED_MIN:
        return "GROWING"
    elif repeat_customers < config.TIER_COMMUNITY_MIN:
        return "TRUSTED"
    else:
        return "COMMUNITY_FAVORITE"


def calculate_repeat_score(
    repeat_customers: int,
    config: DemoScoringWeights = DEFAULT_CONFIG,
) -> float:
    """
    Signal 1: Normalize repeat customer count to a 0-100 score.
    Benchmark: Capped at COMMUNITY_FAVORITE threshold (500 customers).
    """
    score = min(max(0, repeat_customers) / config.TIER_COMMUNITY_MIN, 1.0) * 100.0
    return round(score, 2)


def calculate_scan_consistency(
    repeat_customer_timestamps: Optional[list[list[datetime]]] = None,
    intervals_hours: Optional[list[float]] = None,
) -> float:
    """
    Signal 2: Calculate scan-interval consistency from repeat-customer visit timestamps.

    Statistical Approach:
      Uses the Coefficient of Variation (CV = standard_deviation / mean) of visit intervals.
      - Regular, periodic visits (e.g. daily tea or weekly groceries) have standard deviation near 0,
        yielding CV ≈ 0 and consistency_score ≈ 100.
      - Erratic bursts or random gaps result in high CV (>= 1.0), driving the score down to 0.

      Formula:
        consistency_score = max(0.0, min(100.0, (1.0 - CV) * 100.0))

    Accepts:
      - repeat_customer_timestamps: list of timestamp lists per repeat customer.
      - intervals_hours: direct flat list of intervals in hours (useful for testing/benchmarking).
    """
    # Path A: Flat list of intervals provided directly
    if intervals_hours is not None:
        valid_intervals = [i for i in intervals_hours if i >= 0]
        if len(valid_intervals) < 2:
            return 0.0
        mean_val = statistics.mean(valid_intervals)
        if mean_val <= 0:
            return 0.0
        stdev_val = statistics.stdev(valid_intervals)
        cv = stdev_val / mean_val
        score = max(0.0, min(100.0, (1.0 - cv) * 100.0))
        return round(score, 2)

    # Path B: Per-customer timestamp series
    if not repeat_customer_timestamps:
        return 0.0

    customer_scores: list[float] = []

    for timestamps in repeat_customer_timestamps:
        if len(timestamps) < 3:
            # Not a repeat customer (needs >= 3 scans)
            continue

        sorted_ts = sorted(timestamps)
        # Convert intervals to hours
        deltas: list[float] = []
        for i in range(1, len(sorted_ts)):
            t1 = sorted_ts[i - 1]
            t2 = sorted_ts[i]
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
            delta_h = (t2 - t1).total_seconds() / 3600.0
            if delta_h >= 0:
                deltas.append(delta_h)

        if len(deltas) < 2:
            continue

        mean_interval = statistics.mean(deltas)
        if mean_interval <= 0:
            # 0-second bot bursts are penalized as non-consistent
            customer_scores.append(0.0)
            continue

        stdev_interval = statistics.stdev(deltas)
        cv = stdev_interval / mean_interval
        score = max(0.0, min(100.0, (1.0 - cv) * 100.0))
        customer_scores.append(score)

    if not customer_scores:
        return 0.0

    avg_score = sum(customer_scores) / len(customer_scores)
    return round(avg_score, 2)


def calculate_tenure_score(
    created_at: datetime,
    current_date: Optional[datetime] = None,
    config: DemoScoringWeights = DEFAULT_CONFIG,
) -> tuple[int, float]:
    """
    Signal 3: Calculate vendor tenure from vendor created_at until current date.
    Normalizes tenure days to a 0-100 scale (benchmark: 365 days = 100).
    """
    if current_date is None:
        current_date = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if current_date.tzinfo is None:
        current_date = current_date.replace(tzinfo=timezone.utc)

    delta_days = max(0, (current_date - created_at).days)
    score = min(delta_days / config.MAX_TENURE_BENCHMARK_DAYS, 1.0) * 100.0
    return delta_days, round(score, 2)


def calculate_dispute_score(
    dispute_count: int,
    total_transactions: int,
    config: DemoScoringWeights = DEFAULT_CONFIG,
) -> tuple[float, float]:
    """
    Signal 4: Calculate dispute rate = dispute_count / total_transactions.
    Lower dispute rate contributes positively to the score.
      - 0.0% dispute rate -> 100.0 score (perfect)
      - >= MAX_DISPUTE_TOLERANCE_RATE (5%) -> 0.0 score
    """
    if total_transactions <= 0:
        # No transactions yet -> dispute rate is 0.0, clean score 100.0
        return 0.0, 100.0

    dispute_rate = max(0.0, dispute_count / total_transactions)
    # Normalized penalty
    ratio = min(dispute_rate / config.MAX_DISPUTE_TOLERANCE_RATE, 1.0)
    score = (1.0 - ratio) * 100.0
    return round(dispute_rate, 4), round(score, 2)


# =============================================================================
# 4. PURE TRUST ENGINE SERVICE
# =============================================================================

class TrustEngine:
    """
    TrustEngine handles the pure statistical calculations and tier classifications
    completely detached from database operations.
    """

    config: DemoScoringWeights = DEFAULT_CONFIG

    @classmethod
    def calculate(
        cls,
        repeat_customers: int,
        consistency_score: float = 0.0,
        tenure_score: float = 0.0,
        dispute_score: float = 100.0,
        config: Optional[DemoScoringWeights] = None,
    ) -> dict[str, Any]:
        """
        Process the four normalized signals into a composite trust score,
        assign tier, and apply privacy gating.

        Returns exact dictionary format:
        {
            "trust_score": float,
            "tier": str,
            "badge_visible": bool,
            "repeat_customers": int,
            "consistency_score": float,
            "tenure_score": float,
            "dispute_score": float
        }
        """
        cfg = config or cls.config

        # ── Step 1: Internal trust state calculation ─────────────────────────
        repeat_score = calculate_repeat_score(repeat_customers, cfg)

        composite = (
            (repeat_score * cfg.REPEAT_CUSTOMER_WEIGHT)
            + (consistency_score * cfg.CONSISTENCY_WEIGHT)
            + (tenure_score * cfg.TENURE_WEIGHT)
            + (dispute_score * cfg.DISPUTE_WEIGHT)
        )
        trust_score = round(max(0.0, min(100.0, composite)), 2)
        tier = assign_tier(repeat_customers, cfg)

        # ── Step 2: Privacy gating (K-Anonymity) ──────────────────────────────
        # Trust calculation and privacy gating are two separate concepts.
        # First calculate internal trust state, then apply privacy floor:
        if repeat_customers < cfg.K_ANONYMITY_FLOOR:
            badge_visible = False
        else:
            badge_visible = True

        return {
            "trust_score": trust_score,
            "tier": tier,
            "badge_visible": badge_visible,
            "repeat_customers": repeat_customers,
            "consistency_score": round(consistency_score, 2),
            "tenure_score": round(tenure_score, 2),
            "dispute_score": round(dispute_score, 2),
        }

    @classmethod
    def to_customer_facing_response(
        cls,
        engine_output: dict[str, Any],
        config: Optional[DemoScoringWeights] = None,
    ) -> dict[str, Any]:
        """
        Transform internal trust engine output into a customer-facing response.
        Enforces privacy guarantee: Small repeat-customer counts below 5
        are NEVER exposed to customers.
        """
        cfg = config or cls.config
        badge_visible = engine_output.get("badge_visible", False)
        repeat_customers = engine_output.get("repeat_customers", 0)
        tier = engine_output.get("tier", "NEW")
        meta = TIER_META.get(tier, {"label": "New Vendor", "description": None})

        # Privacy gating check
        if not badge_visible or repeat_customers < cfg.K_ANONYMITY_FLOOR:
            return {
                "badge_visible": False,
                "tier": "NEW",
                "tier_label": meta["label"],
                "tier_description": None,
                "trust_score": None,
                "repeat_customers": None,  # Masked for customer privacy
                "consistency_score": None,
                "tenure_score": None,
                "dispute_score": None,
            }

        return {
            "badge_visible": True,
            "tier": tier,
            "tier_label": meta["label"],
            "tier_description": meta["description"],
            "trust_score": engine_output.get("trust_score"),
            "repeat_customers": repeat_customers,
            "consistency_score": engine_output.get("consistency_score"),
            "tenure_score": engine_output.get("tenure_score"),
            "dispute_score": engine_output.get("dispute_score"),
        }


# =============================================================================
# 5. ASYNC DATABASE INTEGRATION PIPELINE
# =============================================================================

async def recalculate_trust(vendor_id: str) -> BadgePayload:
    """
    Full database orchestration pipeline for a vendor. Called after scan events.

    Steps:
      1. Aggregate scan_events collection via MongoDB aggregation
      2. Identify repeat customers (scanned >= 3 times) and extract their visit timestamps
      3. Compute scan-interval consistency score using statistical CV
      4. Fetch vendor document for created_at (tenure) and dispute_count
      5. Run TrustEngine.calculate() to produce standardized metrics
      6. Upsert computed stats into vendor_stats collection
      7. Return privacy-safe BadgePayload for WebSocket broadcast
    """
    scans = scan_events_col()
    stats_col = vendor_stats_col()
    vend_col = vendors_col()

    now = datetime.now(timezone.utc)

    # ── Step 1 & 2: Modular Aggregation Layer (via services/aggregator.py) ─────
    from app.services.aggregator import aggregate_vendor_scans

    agg = await aggregate_vendor_scans(vendor_id)
    total_scans = agg["total_scans"]
    unique_scanners = agg["unique_scanners"]
    repeat_customers = agg["repeat_customers"]
    repeat_timestamps = agg["repeat_timestamps"]
    avg_scan_interval_hours = agg["avg_scan_interval_hours"]

    # ── Step 3: Compute scan consistency from repeat customers ───────────────
    consistency_score = calculate_scan_consistency(repeat_timestamps)


    # ── Step 4: Fetch vendor tenure and dispute data ─────────────────────────
    vendor_doc = await vend_col.find_one({"vendor_id": vendor_id})
    dispute_count = vendor_doc.get("dispute_count", 0) if vendor_doc else 0
    total_tx = vendor_doc.get("total_transactions", total_scans) if vendor_doc else total_scans
    vendor_created_at = vendor_doc.get("created_at", now) if vendor_doc else now

    tenure_days, tenure_score = calculate_tenure_score(vendor_created_at, now)
    dispute_rate, dispute_score = calculate_dispute_score(dispute_count, total_tx)

    # ── Step 5: Pure TrustEngine calculation ──────────────────────────────────
    metrics = TrustEngine.calculate(
        repeat_customers=repeat_customers,
        consistency_score=consistency_score,
        tenure_score=tenure_score,
        dispute_score=dispute_score,
    )

    trust_score = metrics["trust_score"]
    trust_tier: TrustTier = metrics["tier"]
    badge_visible = metrics["badge_visible"]

    # ── Step 6: Upsert vendor_stats ───────────────────────────────────────────
    await stats_col.update_one(
        {"vendor_id": vendor_id},
        {
            "$set": {
                "vendor_id": vendor_id,
                "total_scans": total_scans,
                "unique_scanners": unique_scanners,
                "repeat_customers": repeat_customers,
                "avg_scan_interval_hours": avg_scan_interval_hours,
                "tenure_days": tenure_days,
                "trust_score": trust_score,
                "trust_tier": trust_tier,
                "badge_visible": badge_visible,
                "consistency_score": consistency_score,
                "tenure_score": tenure_score,
                "dispute_score": dispute_score,
                "dispute_rate": dispute_rate,
                "last_updated": now,
            }
        },
        upsert=True,
    )
    from app.database import save_mock_db
    await save_mock_db()

    # ── Step 7: Build privacy-safe BadgePayload & broadcast ───────────────────
    meta = TIER_META[trust_tier]
    badge = BadgePayload(
        vendor_id=vendor_id,
        badge_visible=badge_visible,
        trust_tier=trust_tier,
        tier_label=meta["label"],
        tier_description=meta["description"] if badge_visible else None,
        total_scans_approx=_bucket_scans(total_scans) if badge_visible else None,
        tenure_days=tenure_days if badge_visible else None,
    )

    from app.websocket.manager import ws_manager
    await ws_manager.broadcast_trust_update(
        vendor_id=vendor_id,
        tier=trust_tier,
        badge_visible=badge_visible,
        trust_score=trust_score,
        repeat_customers=repeat_customers,
        tier_label=meta["label"],
        tier_description=meta["description"] if badge_visible else None,
        total_scans_approx=_bucket_scans(total_scans) if badge_visible else None,
        tenure_days=tenure_days,
        total_scans=total_scans,
        consistency_score=consistency_score,
        dispute_rate=dispute_rate,
        last_updated=now.isoformat(),
    )
    await ws_manager.broadcast(vendor_id, badge.model_dump())

    return badge
