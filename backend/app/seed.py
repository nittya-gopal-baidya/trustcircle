"""
app/seed.py
-----------
Seed utility to populate realistic demo data across all four TrustCircle tiers:

  1. New vendor (< 5 repeat customers)
     - ID: sharma_chai_001 ("Sharma Chai Corner", Jaipur)
     - Repeat customers: 2 (below k-anonymity floor k=5)
     - Tier: NEW
     - Badge: NO TRUST BADGE ("Building history...", badge_visible = False)

  2. Growing vendor (between 5 and 49 repeat customers)
     - ID: vendor_growing_cafe ("Ravi's Breakfast & Chai", Mumbai)
     - Repeat customers: 22
     - Tier: GROWING
     - Badge: GROWING ("5+ regulars trust this vendor", badge_visible = True)

  3. Trusted vendor (between 50 and 499 repeat customers)
     - ID: vendor_trusted_kirana ("Gupta Kirana & General Store", Delhi)
     - Repeat customers: 130
     - Tier: TRUSTED
     - Badge: TRUSTED ("50+ regulars trust this vendor", badge_visible = True)

  4. Community Favorite (500+ repeat customers)
     - ID: vendor_community_sweets ("Jodhpur Sweets & Namkeen", Jaipur)
     - Repeat customers: 560
     - Tier: COMMUNITY_FAVORITE
     - Badge: COMMUNITY FAVORITE ("500+ regulars trust this community favorite", badge_visible = True)

For each vendor, all four core signals are calculated:
  - Signal 1: Unique repeat customers (scanned >= 3 times)
  - Signal 2: Scan-interval consistency (standard deviation of visit intervals)
  - Signal 3: Vendor tenure (days since onboarding benchmarked against 365 days)
  - Signal 4: Dispute/chargeback rate (dispute_count / total_transactions)

Usage:
  python -m app.seed
"""

import asyncio
import hashlib
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.database import (
    close_db,
    connect_db,
    get_db,
    save_mock_db,
    scan_events_col,
    vendor_stats_col,
    vendors_col,
)
from app.services.trust_engine import (
    DEFAULT_CONFIG,
    TIER_META,
    TrustEngine,
    _bucket_scans,
    calculate_dispute_score,
    calculate_scan_consistency,
    calculate_tenure_score,
)


def _hash(raw_id: str) -> str:
    """Deterministic customer hash representing client-side device privacy."""
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


@dataclass
class VendorSeedDefinition:
    vendor_id: str
    name: str
    category: str
    city: str
    tier_target: str
    days_active: int
    repeat_customers_count: int
    one_time_customers_count: int
    min_amount: float
    max_amount: float
    avg_interval_hours: float
    interval_variance_hours: float
    dispute_count: int
    description: str


DEMO_VENDOR_DEFINITIONS: list[VendorSeedDefinition] = [
    # ── 1. NEW VENDOR (< 5 repeat customers) ─────────────────────────────────
    VendorSeedDefinition(
        vendor_id="sharma_chai_001",
        name="Sharma Chai Corner",
        category="Tea Stall",
        city="Jaipur",
        tier_target="NEW",
        days_active=21,                     # ~3 weeks operating
        repeat_customers_count=2,           # 2 repeat customers (< 5 k-anonymity floor)
        one_time_customers_count=6,         # 6 walk-in customers
        min_amount=15.0,
        max_amount=40.0,
        avg_interval_hours=24.0,            # Daily tea interval
        interval_variance_hours=0.5,
        dispute_count=0,
        description="Fresh roadside tea stall building its initial patron base.",
    ),

    # ── 2. GROWING VENDOR (5–49 repeat customers) ────────────────────────────
    VendorSeedDefinition(
        vendor_id="vendor_growing_cafe",
        name="Ravi's Breakfast & Chai",
        category="Quick Service Cafe",
        city="Mumbai",
        tier_target="GROWING",
        days_active=135,                    # ~4.5 months operating
        repeat_customers_count=22,          # 22 repeat customers (5–49)
        one_time_customers_count=25,        # 25 casual customers
        min_amount=25.0,
        max_amount=120.0,
        avg_interval_hours=24.0,            # Daily breakfast routine
        interval_variance_hours=0.8,
        dispute_count=0,
        description="Popular neighborhood snack bar with a growing morning regular crowd.",
    ),

    # ── 3. TRUSTED VENDOR (50–499 repeat customers) ──────────────────────────
    VendorSeedDefinition(
        vendor_id="vendor_trusted_kirana",
        name="Gupta Kirana & General Store",
        category="Daily Grocery & Provisions",
        city="Delhi",
        tier_target="TRUSTED",
        days_active=460,                    # ~1.3 years operating (mature)
        repeat_customers_count=130,         # 130 repeat customers (50–499)
        one_time_customers_count=80,        # 80 one-off shoppers
        min_amount=80.0,
        max_amount=650.0,
        avg_interval_hours=48.0,            # Bi-daily grocery replenishment
        interval_variance_hours=2.5,
        dispute_count=1,                    # 1 minor dispute across ~500+ tx
        description="Established neighborhood provision store trusted by local families.",
    ),

    # ── 4. COMMUNITY FAVORITE VENDOR (500+ repeat customers) ─────────────────
    VendorSeedDefinition(
        vendor_id="vendor_community_sweets",
        name="Jodhpur Sweets & Namkeen",
        category="Heritage Confectionery",
        city="Jaipur",
        tier_target="COMMUNITY_FAVORITE",
        days_active=880,                    # ~2.4 years operating (landmark)
        repeat_customers_count=560,         # 560 repeat customers (500+)
        one_time_customers_count=200,       # 200 festive/tourist buyers
        min_amount=120.0,
        max_amount=1200.0,
        avg_interval_hours=72.0,            # Regular sweet/savory runs
        interval_variance_hours=4.0,
        dispute_count=2,                    # 2 chargebacks across ~2,200+ tx (0.09%)
        description="Legendary landmark confectioner with a massive multi-year loyal community.",
    ),
]


async def generate_vendor_scans_and_stats(
    defn: VendorSeedDefinition,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """
    Generate realistic simulated scans and calculate all 4 signals strictly
    according to the TrustCircle concept.
    """
    # Deterministic pseudo-random seed per vendor for consistent reproducibility
    rng = random.Random(hash(defn.vendor_id) & 0xFFFFFFFF)

    created_at = now - timedelta(days=defn.days_active)
    scan_docs: list[dict[str, Any]] = []
    repeat_customer_timestamps: list[list[datetime]] = []

    # 1. Generate repeat customer scan series (each customer visits >= 3 times)
    for i in range(defn.repeat_customers_count):
        cust_id = f"sim_cust_{defn.vendor_id}_{i+1:04d}"
        cust_hash = _hash(cust_id)

        # 3 to 5 visits per repeat customer
        visit_count = rng.randint(3, 5)
        # First visit occurred between created_at and 10 days ago
        start_days_ago = rng.uniform(min(defn.days_active - 1, 90), 10)
        base_time = now - timedelta(days=start_days_ago)

        current_visit = base_time.replace(
            hour=rng.randint(8, 20),
            minute=rng.randint(0, 59),
            second=rng.randint(0, 59),
            microsecond=0,
        )

        customer_ts: list[datetime] = []
        for v_idx in range(visit_count):
            if v_idx > 0:
                # Interval = average interval with subtle natural variance
                gap = defn.avg_interval_hours + rng.uniform(
                    -defn.interval_variance_hours, defn.interval_variance_hours
                )
                current_visit += timedelta(hours=max(1.0, gap))
                if current_visit > now:
                    current_visit = now - timedelta(minutes=rng.randint(5, 60))

            amount = round(rng.uniform(defn.min_amount, defn.max_amount), 2)
            scan_docs.append({
                "vendor_id": defn.vendor_id,
                "customer_hash": cust_hash,
                "timestamp": current_visit,
                "amount": amount,
            })
            customer_ts.append(current_visit)

        repeat_customer_timestamps.append(customer_ts)

    # 2. Generate one-time/occasional customer scans (< 3 visits each)
    for i in range(defn.one_time_customers_count):
        cust_id = f"sim_walkin_{defn.vendor_id}_{i+1:04d}"
        cust_hash = _hash(cust_id)
        # 1 or 2 visits (does NOT qualify as a repeat customer)
        visit_count = rng.choice([1, 1, 1, 2])
        for _ in range(visit_count):
            days_ago = rng.uniform(0.1, defn.days_active)
            scan_time = now - timedelta(days=days_ago)
            amount = round(rng.uniform(defn.min_amount, defn.max_amount), 2)
            scan_docs.append({
                "vendor_id": defn.vendor_id,
                "customer_hash": cust_hash,
                "timestamp": scan_time,
                "amount": amount,
            })

    total_scans = len(scan_docs)
    unique_scanners = defn.repeat_customers_count + defn.one_time_customers_count
    repeat_customers = defn.repeat_customers_count

    # ── Signal 2: Scan-interval consistency ──────────────────────────────────
    consistency_score = calculate_scan_consistency(repeat_customer_timestamps)
    if repeat_customers < 3:
        consistency_score = 0.0 if repeat_customers == 0 else 85.0

    # Average scan interval in hours
    avg_scan_interval_hours = defn.avg_interval_hours if repeat_customers > 0 else 0.0

    # ── Signal 3: Vendor tenure ──────────────────────────────────────────────
    tenure_days, tenure_score = calculate_tenure_score(created_at, now)

    # ── Signal 4: Dispute/chargeback rate ────────────────────────────────────
    dispute_rate, dispute_score = calculate_dispute_score(defn.dispute_count, total_scans)

    # ── Trust Engine composite calculation ───────────────────────────────────
    trust_result = TrustEngine.calculate(
        repeat_customers=repeat_customers,
        consistency_score=consistency_score,
        tenure_score=tenure_score,
        dispute_score=dispute_score,
    )

    trust_tier = trust_result["tier"]
    badge_visible = trust_result["badge_visible"]
    trust_score = trust_result["trust_score"]

    # Verify that the tier matches target
    assert trust_tier == defn.tier_target, (
        f"Tier mismatch for {defn.vendor_id}: got {trust_tier}, expected {defn.tier_target}"
    )

    vendor_doc = {
        "vendor_id": defn.vendor_id,
        "name": defn.name,
        "category": defn.category,
        "city": defn.city,
        "created_at": created_at,
        "dispute_count": defn.dispute_count,
        "total_transactions": total_scans,
        "description": defn.description,
    }

    vendor_stats_doc = {
        "vendor_id": defn.vendor_id,
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

    return vendor_doc, vendor_stats_doc, scan_docs


async def seed_all(verbose: bool = True) -> list[dict[str, Any]]:
    """
    Main seed function: connects to MongoDB and inserts realistic seed data
    for all four demo tiers.
    """
    await connect_db()
    db = get_db()
    now = datetime.now(timezone.utc)

    # Ensure required indexes
    await db["scan_events"].create_index([("vendor_id", 1), ("customer_hash", 1)])
    await db["scan_events"].create_index([("vendor_id", 1), ("timestamp", -1)])
    await db["vendor_stats"].create_index([("vendor_id", 1)], unique=True)
    await db["vendors"].create_index([("vendor_id", 1)], unique=True)

    seeded_summaries: list[dict[str, Any]] = []

    if verbose:
        print("=" * 80)
        print("          TRUSTCIRCLE MULTI-TIER VENDOR SEED UTILITY")
        print("=" * 80)
        print(f"Target Database: {db.name} | Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    for idx, defn in enumerate(DEMO_VENDOR_DEFINITIONS, start=1):
        # 1. Clean existing records for this vendor
        await scan_events_col().delete_many({"vendor_id": defn.vendor_id})
        await vendor_stats_col().delete_many({"vendor_id": defn.vendor_id})

        # 2. Generate simulated scans and calculated stats
        vendor_doc, vendor_stats_doc, scan_docs = await generate_vendor_scans_and_stats(defn, now)

        # 3. Insert vendor profile
        await vendors_col().update_one(
            {"vendor_id": defn.vendor_id},
            {"$set": vendor_doc},
            upsert=True,
        )

        # 4. Insert vendor stats
        await vendor_stats_col().update_one(
            {"vendor_id": defn.vendor_id},
            {"$set": vendor_stats_doc},
            upsert=True,
        )

        # 5. Bulk insert scan events in chunks of 1000
        if scan_docs:
            chunk_size = 1000
            for c_idx in range(0, len(scan_docs), chunk_size):
                await scan_events_col().insert_many(scan_docs[c_idx : c_idx + chunk_size])

        tier = vendor_stats_doc["trust_tier"]
        meta = TIER_META[tier]
        visible = vendor_stats_doc["badge_visible"]

        summary = {
            "step": idx,
            "tier": tier,
            "vendor_id": defn.vendor_id,
            "name": defn.name,
            "category": defn.category,
            "city": defn.city,
            "total_scans": vendor_stats_doc["total_scans"],
            "unique_scanners": vendor_stats_doc["unique_scanners"],
            "repeat_customers": vendor_stats_doc["repeat_customers"],
            "consistency_score": vendor_stats_doc["consistency_score"],
            "tenure_days": vendor_stats_doc["tenure_days"],
            "tenure_score": vendor_stats_doc["tenure_score"],
            "dispute_rate": vendor_stats_doc["dispute_rate"],
            "dispute_score": vendor_stats_doc["dispute_score"],
            "trust_score": vendor_stats_doc["trust_score"],
            "badge_visible": visible,
            "badge_label": meta["label"],
            "badge_desc": meta["description"] if visible else "Building history...",
        }
        seeded_summaries.append(summary)

        if verbose:
            privacy_status = "Visible (k >= 5)" if visible else "Hidden (k < 5 Privacy Gate Active)"
            print(f"[{idx}/4] {tier.replace('_', ' ')} VENDOR")
            print(f"      Vendor:       {defn.name} (ID: {defn.vendor_id})")
            print(f"      Category:     {defn.category} | {defn.city}")
            print(f"      Tenure:       {vendor_stats_doc['tenure_days']} days (Score: {vendor_stats_doc['tenure_score']:.1f}/100)")
            print(f"      Disputes:     {defn.dispute_count} / {vendor_stats_doc['total_scans']} ({vendor_stats_doc['dispute_rate']:.2%} dispute rate, Score: {vendor_stats_doc['dispute_score']:.1f}/100)")
            print(f"      Scans:        {vendor_stats_doc['total_scans']} total, {vendor_stats_doc['unique_scanners']} unique, {vendor_stats_doc['repeat_customers']} repeat customers")
            print(f"      Consistency:  {vendor_stats_doc['consistency_score']:.1f}%")
            print(f"      Trust Score:  {vendor_stats_doc['trust_score']:.1f} / 100")
            print(f"      Trust Tier:   {tier} [{privacy_status}]")
            print(f"      Badge Label:  {meta['label']} -> \"{meta['description'] if visible else 'Building history...'}\"")
            print("-" * 80)

    if verbose:
        print("=" * 80)
        print(" SUCCESS: All 4 TrustCircle tiers successfully seeded in MongoDB!")
        print("=" * 80)
        print(" You can now test any vendor via:")
        print("   - API:  GET http://localhost:8000/api/vendors/{vendor_id}/stats")
        print("   - WS:   ws://localhost:8000/ws/vendor/{vendor_id}")
        print("   - UI:   http://localhost:5173 (Select vendor from dropdown/tabs)")
        print("=" * 80)

    await save_mock_db()
    await close_db()
    return seeded_summaries


def main():
    """CLI entry point for python -m app.seed"""
    try:
        asyncio.run(seed_all(verbose=True))
    except KeyboardInterrupt:
        print("\n[Seed] Interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[Seed] Error during seeding: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
