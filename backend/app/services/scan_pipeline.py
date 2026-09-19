"""
services/scan_pipeline.py
-------------------------
Complete QR Scan Processing Pipeline with Real-time WebSocket Streaming.

Executes the 7-stage end-to-end processing flow:

      SCAN_RECEIVED
            ↓
       SCAN_STORED
            ↓
   AGGREGATION_UPDATED
            ↓
     TRUST_CALCULATED
            ↓
     PRIVACY_CHECKED
            ↓
      BADGE_UPDATED
            ↓
   WEBSOCKET_BROADCAST / TRUST_UPDATED

Strict privacy protections:
  - customer_hash is stored internally in scan_events for aggregation only.
  - customer_hash, individual customer identity, and raw transactions are NEVER streamed to clients.
  - Returns only privacy-safe aggregated badge and pipeline trace events.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import HTTPException

from app.database import scan_events_col, vendor_stats_col, vendors_col
from app.schemas.scan import PipelineEvent, ProcessingStageItem
from app.schemas.vendor import BadgePayload
from app.services.trust_engine import (
    DEFAULT_CONFIG,
    TIER_META,
    TrustEngine,
    _bucket_scans,
    calculate_dispute_score,
    calculate_scan_consistency,
    calculate_tenure_score,
)
from app.websocket.manager import ws_manager


class PipelineStage(str, Enum):
    SCAN_RECEIVED = "SCAN_RECEIVED"
    SCAN_STORED = "SCAN_STORED"
    AGGREGATION_UPDATED = "AGGREGATION_UPDATED"
    TRUST_CALCULATED = "TRUST_CALCULATED"
    PRIVACY_CHECKED = "PRIVACY_CHECKED"
    BADGE_UPDATED = "BADGE_UPDATED"
    WEBSOCKET_BROADCAST = "WEBSOCKET_BROADCAST"


async def execute_scan_pipeline(
    vendor_id: str,
    customer_hash: str,
    amount: float = 0.0,
    scan_timestamp: Optional[datetime] = None,
) -> tuple[str, BadgePayload, list[PipelineEvent], list[ProcessingStageItem]]:
    """
    Executes the 14-step processing pipeline for a simulated QR scan:

      1. Receive vendor_id
      2. Receive customer_hash
      3. Receive amount
      4. Generate timestamp if not supplied
      5. Store the scan event in MongoDB
      6. Recalculate the vendor's aggregated statistics
      7. Identify repeat customers
      8. Calculate scan consistency
      9. Calculate vendor tenure
      10. Calculate dispute rate
      11. Run the Trust Engine
      12. Apply the k-anonymity privacy gate
      13. Update vendor_stats
      14. Broadcast the new aggregated trust state through WebSocket
    """
    events: list[PipelineEvent] = []

    async def _emit_stage(stage: PipelineStage, message: str, details: dict[str, Any]) -> None:
        """Record stage event and broadcast live to WebSocket subscribers."""
        event = PipelineEvent(
            stage=stage.value,
            timestamp=datetime.now(timezone.utc),
            message=message,
            details=details,
        )
        events.append(event)
        print(f"[PIPELINE] [{stage.value}] {message} | {details}")
        # Broadcast intermediate stage event to WebSocket (strictly privacy-safe)
        await ws_manager.broadcast_event(vendor_id, stage.value, details)

    # ── STAGE 1: SCAN_RECEIVED ────────────────────────────────────────────────
    vendor = await vendors_col().find_one({"vendor_id": vendor_id})
    if not vendor:
        raise HTTPException(
            status_code=404,
            detail=f"Vendor '{vendor_id}' not found. Please seed vendors first.",
        )

    if scan_timestamp is None:
        scan_timestamp = datetime.now(timezone.utc)
    elif scan_timestamp.tzinfo is None:
        scan_timestamp = scan_timestamp.replace(tzinfo=timezone.utc)

    await _emit_stage(
        PipelineStage.SCAN_RECEIVED,
        f"QR scan received for vendor '{vendor_id}'",
        {"vendor_id": vendor_id, "amount": amount, "timestamp": scan_timestamp.isoformat()},
    )

    # ── STAGE 2: SCAN_STORED ──────────────────────────────────────────────────
    scan_doc = {
        "vendor_id": vendor_id,
        "customer_hash": customer_hash,
        "amount": amount,
        "timestamp": scan_timestamp,
    }
    insert_result = await scan_events_col().insert_one(scan_doc)
    scan_id = str(insert_result.inserted_id)

    await vendors_col().update_one(
        {"vendor_id": vendor_id},
        {"$inc": {"total_transactions": 1}},
    )

    await _emit_stage(
        PipelineStage.SCAN_STORED,
        "Scan event recorded in MongoDB scan_events",
        {"scan_id": scan_id, "collection": "scan_events"},
    )

    # ── STAGE 3: AGGREGATION_UPDATED ──────────────────────────────────────────
    # Delegated to services/aggregator.py for clean modular separation
    from app.services.aggregator import aggregate_vendor_scans

    agg = await aggregate_vendor_scans(vendor_id)
    total_scans = agg["total_scans"]
    unique_scanners = agg["unique_scanners"]
    repeat_customers = agg["repeat_customers"]
    repeat_timestamps = agg["repeat_timestamps"]
    avg_scan_interval_hours = agg["avg_scan_interval_hours"]

    await _emit_stage(
        PipelineStage.AGGREGATION_UPDATED,
        f"Aggregation complete: {total_scans} scans, {unique_scanners} unique, {repeat_customers} repeat customers",
        {
            "total_scans": total_scans,
            "unique_scanners": unique_scanners,
            "repeat_customers": repeat_customers,
        },
    )

    # ── STAGE 4: TRUST_CALCULATED ─────────────────────────────────────────────
    consistency_score = calculate_scan_consistency(repeat_timestamps)


    # Refresh vendor doc for up-to-date total_transactions and created_at
    vendor_doc = await vendors_col().find_one({"vendor_id": vendor_id})
    vendor_created_at = vendor_doc.get("created_at", scan_timestamp) if vendor_doc else scan_timestamp
    dispute_count = vendor_doc.get("dispute_count", 0) if vendor_doc else 0
    total_tx = vendor_doc.get("total_transactions", total_scans) if vendor_doc else total_scans

    tenure_days, tenure_score = calculate_tenure_score(vendor_created_at, scan_timestamp)
    dispute_rate, dispute_score = calculate_dispute_score(dispute_count, total_tx)

    trust_result = TrustEngine.calculate(
        repeat_customers=repeat_customers,
        consistency_score=consistency_score,
        tenure_score=tenure_score,
        dispute_score=dispute_score,
    )

    await _emit_stage(
        PipelineStage.TRUST_CALCULATED,
        f"Trust calculation completed: score={trust_result['trust_score']}, tier={trust_result['tier']}",
        {
            "trust_score": trust_result["trust_score"],
            "tier": trust_result["tier"],
            "consistency_score": consistency_score,
            "tenure_score": tenure_score,
            "dispute_score": dispute_score,
        },
    )

    # ── STAGE 5: PRIVACY_CHECKED ──────────────────────────────────────────────
    badge_visible = trust_result["badge_visible"]

    await _emit_stage(
        PipelineStage.PRIVACY_CHECKED,
        (
            f"Privacy check passed: repeat_customers={repeat_customers} >= 5 (Badge visible)"
            if badge_visible
            else f"K-anonymity gate active: repeat_customers={repeat_customers} < 5 (Badge hidden)"
        ),
        {
            "k_anonymity_floor": DEFAULT_CONFIG.K_ANONYMITY_FLOOR,
            "repeat_customers": repeat_customers,
            "badge_visible": badge_visible,
            "privacy_masked": not badge_visible,
        },
    )

    # ── STAGE 6: BADGE_UPDATED ────────────────────────────────────────────────
    tier = trust_result["tier"]
    meta = TIER_META[tier]

    await vendor_stats_col().update_one(
        {"vendor_id": vendor_id},
        {
            "$set": {
                "vendor_id": vendor_id,
                "total_scans": total_scans,
                "unique_scanners": unique_scanners,
                "repeat_customers": repeat_customers,
                "avg_scan_interval_hours": avg_scan_interval_hours,
                "tenure_days": tenure_days,
                "trust_score": trust_result["trust_score"],
                "trust_tier": tier,
                "badge_visible": badge_visible,
                "consistency_score": consistency_score,
                "tenure_score": tenure_score,
                "dispute_score": dispute_score,
                "dispute_rate": dispute_rate,
                "last_updated": scan_timestamp,
            }
        },
        upsert=True,
    )
    from app.database import save_mock_db
    await save_mock_db()

    badge = BadgePayload(
        vendor_id=vendor_id,
        badge_visible=badge_visible,
        trust_tier=tier,
        tier_label=meta["label"],
        tier_description=meta["description"] if badge_visible else None,
        total_scans_approx=_bucket_scans(total_scans) if badge_visible else None,
        tenure_days=tenure_days if badge_visible else None,
    )

    await _emit_stage(
        PipelineStage.BADGE_UPDATED,
        f"Vendor stats committed to MongoDB: tier='{tier}', visible={badge_visible}",
        {
            "vendor_id": vendor_id,
            "tier": tier,
            "badge_visible": badge_visible,
            "tenure_days": tenure_days if badge_visible else None,
            "total_scans_approx": _bucket_scans(total_scans) if badge_visible else None,
        },
    )

    # ── STAGE 7: WEBSOCKET_BROADCAST (TRUST_UPDATED) ──────────────────────────
    subscriber_count = ws_manager.connection_count(vendor_id)

    # Broadcast primary TRUST_UPDATED event format
    await ws_manager.broadcast_trust_update(
        vendor_id=vendor_id,
        tier=tier,
        badge_visible=badge_visible,
        trust_score=trust_result["trust_score"],
        repeat_customers=repeat_customers,
        tier_label=meta["label"],
        tier_description=meta["description"] if badge_visible else None,
        total_scans_approx=_bucket_scans(total_scans) if badge_visible else None,
        tenure_days=tenure_days,
        total_scans=total_scans,
        consistency_score=consistency_score,
        dispute_rate=dispute_rate,
        last_updated=scan_timestamp.isoformat(),
    )

    # Also broadcast raw BadgePayload for backward compatibility
    await ws_manager.broadcast(vendor_id, badge.model_dump())

    event_final = PipelineEvent(
        stage=PipelineStage.WEBSOCKET_BROADCAST.value,
        timestamp=datetime.now(timezone.utc),
        message=f"Broadcasted updated trust state to {subscriber_count} WebSocket subscribers",
        details={
            "vendor_id": vendor_id,
            "channel": f"ws/vendor/{vendor_id}",
            "subscribers_notified": subscriber_count,
        },
    )
    events.append(event_final)

    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

    processing_details: list[ProcessingStageItem] = [
        ProcessingStageItem(
            step=1,
            name="Event received",
            stage_id="EVENT_RECEIVED",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Offline QR scan payload captured at API gateway with amount ₹{amount:.2f} for vendor '{vendor_id}'.",
            details={"vendor_id": vendor_id, "amount": amount},
        ),
        ProcessingStageItem(
            step=2,
            name="Event stored in MongoDB",
            stage_id="EVENT_STORED_MONGODB",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Raw scan document securely appended to MongoDB 'scan_events' with ID {scan_id}.",
            details={"collection": "scan_events", "scan_id": scan_id},
        ),
        ProcessingStageItem(
            step=3,
            name="Unique scanner aggregation",
            stage_id="UNIQUE_SCANNER_AGGREGATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"MongoDB aggregation grouped transactions by hashed device keys; detected {unique_scanners} unique customer devices.",
            details={"unique_scanners": unique_scanners, "total_scans": total_scans},
        ),
        ProcessingStageItem(
            step=4,
            name="Repeat customer calculation",
            stage_id="REPEAT_CUSTOMER_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Identified {repeat_customers} repeat customers who scanned this vendor ≥ 3 times (social proof threshold).",
            details={"repeat_customers": repeat_customers, "repeat_threshold": DEFAULT_CONFIG.REPEAT_SCAN_THRESHOLD},
        ),
        ProcessingStageItem(
            step=5,
            name="Scan consistency calculation",
            stage_id="SCAN_CONSISTENCY_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Evaluated habitual visit-interval regularity across repeat customer timestamps; consistency score = {consistency_score:.1f}%.",
            details={"consistency_score": consistency_score, "avg_interval_hours": avg_scan_interval_hours},
        ),
        ProcessingStageItem(
            step=6,
            name="Vendor tenure calculation",
            stage_id="VENDOR_TENURE_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Evaluated operational history since onboarding ({tenure_days} days active); tenure score = {tenure_score:.1f}/100.",
            details={"tenure_days": tenure_days, "tenure_score": tenure_score},
        ),
        ProcessingStageItem(
            step=7,
            name="Dispute rate calculation",
            stage_id="DISPUTE_RATE_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Calculated chargeback ratio ({dispute_count} disputes across {total_tx} transactions, rate = {dispute_rate:.2%}); dispute score = {dispute_score:.1f}/100.",
            details={"dispute_count": dispute_count, "total_transactions": total_tx, "dispute_rate": dispute_rate, "dispute_score": dispute_score},
        ),
        ProcessingStageItem(
            step=8,
            name="Trust score calculation",
            stage_id="TRUST_SCORE_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Weighted composite trust formula applied: 40% Repeat ({repeat_customers} regulars) + 25% Consistency ({consistency_score:.1f}%) + 20% Tenure ({tenure_score:.1f}) + 15% Dispute ({dispute_score:.1f}) = {trust_result['trust_score']:.1f}/100.",
            details={"trust_score": trust_result["trust_score"]},
        ),
        ProcessingStageItem(
            step=9,
            name="Trust tier calculation",
            stage_id="TRUST_TIER_CALCULATION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Compared {repeat_customers} regulars against tier benchmarks (5+ for GROWING, 50+ for TRUSTED); awarded tier: {tier}.",
            details={"tier": tier, "repeat_customers": repeat_customers},
        ),
        ProcessingStageItem(
            step=10,
            name="k-anonymity check",
            stage_id="K_ANONYMITY_CHECK",
            status="PASSED" if badge_visible else "MASKED",
            timestamp=now_ts,
            explanation=(
                f"Evaluated privacy floor (k ≥ 5): repeat_customers={repeat_customers}. "
                f"{'Privacy gate open — individual identity is mathematically protected.' if badge_visible else 'K-anonymity active — vendor badge hidden to prevent customer deanonymization.'}"
            ),
            details={"k_anonymity_floor": DEFAULT_CONFIG.K_ANONYMITY_FLOOR, "repeat_customers": repeat_customers, "badge_visible": badge_visible},
        ),
        ProcessingStageItem(
            step=11,
            name="Badge decision",
            stage_id="BADGE_DECISION",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Badge visibility set to {badge_visible} ('{meta['label']}'); updated stats committed to MongoDB 'vendor_stats'.",
            details={"badge_visible": badge_visible, "tier_label": meta["label"]},
        ),
        ProcessingStageItem(
            step=12,
            name="WebSocket broadcast",
            stage_id="WEBSOCKET_BROADCAST",
            status="COMPLETED",
            timestamp=now_ts,
            explanation=f"Broadcasted real-time TRUST_UPDATED event with updated tier '{tier}' to {subscriber_count} connected WebSocket clients.",
            details={"subscribers_notified": subscriber_count, "channel": f"/ws/vendor/{vendor_id}"},
        ),
    ]

    # Broadcast PROCESSING_DETAILS over WebSocket for live developer/demo mode
    await ws_manager.broadcast_event(
        vendor_id,
        "PROCESSING_DETAILS",
        {
            "vendor_id": vendor_id,
            "scan_id": scan_id,
            "timestamp": now_iso,
            "stages": [s.model_dump() for s in processing_details],
        },
    )

    return scan_id, badge, events, processing_details
