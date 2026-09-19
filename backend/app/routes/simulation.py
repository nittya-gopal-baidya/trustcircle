"""
routes/simulation.py
--------------------
Hackathon Simulation Engine for TrustCircle.

Simulates offline QR scan events and customer behavior patterns:
  - POST /api/simulation/burst   → Generate N repeat customers with realistic multi-visit scans
  - POST /api/simulation/scan    → Generate a single live scan event to demo the 7-stage pipeline
  - POST /api/simulation/reset   → Reset vendor to clean state (NEW tier, badge hidden)

Enables live progressive tier demonstration:
  NEW (0–4 repeat customers)
   ↓ (+5 customers)
  GROWING (5–49 repeat customers)
   ↓ (+50 customers)
  TRUSTED (50–499 repeat customers)
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.database import scan_events_col, vendor_stats_col, vendors_col
from app.schemas.scan import ScanResponse
from app.schemas.simulation import (
    BurstSimulationRequest,
    BurstSimulationResponse,
    ResetRequest,
    ResetResponse,
    SingleScanSimulationRequest,
)
from app.services.scan_pipeline import execute_scan_pipeline
from app.services.trust_engine import recalculate_trust
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/simulation", tags=["Simulation (Hackathon Only)"])


def _hash(raw_id: str) -> str:
    """Compute SHA-256 hash of simulated customer identifier."""
    return hashlib.sha256(raw_id.encode()).hexdigest()


async def _ensure_vendor_exists(vendor_id: str):
    """Ensure target vendor exists in MongoDB, auto-seeding defaults if missing."""
    vendor = await vendors_col().find_one({"vendor_id": vendor_id})
    if not vendor:
        if vendor_id == "sharma_chai_001":
            default_vendor = {
                "vendor_id": "sharma_chai_001",
                "name": "Sharma Chai Corner",
                "category": "Tea Stall",
                "city": "Jaipur",
                "created_at": datetime(2023, 6, 15, tzinfo=timezone.utc),
                "dispute_count": 0,
                "total_transactions": 0,
            }
            await vendors_col().insert_one(default_vendor)
            return default_vendor
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor '{vendor_id}' not found. Seed vendors first."
            )
    return vendor


@router.post("/burst", response_model=BurstSimulationResponse)
async def burst_simulation(payload: BurstSimulationRequest):
    """
    Generate a batch of realistic repeat customers for a vendor.

    Each simulated customer visits the vendor 3 to 5 times at realistic
    habitual intervals (e.g. daily morning chai visits ~24h apart),
    ensuring they qualify as repeat customers (>= 3 scans).

    Allows progressive live demo:
      - 0 repeat customers   → NEW (badge hidden)
      - +5 repeat customers  → GROWING (badge unlocks at K=5)
      - +50 repeat customers → TRUSTED
    """
    vendor = await _ensure_vendor_exists(payload.vendor_id)

    # Determine number of repeat customers to simulate
    num_customers = payload.customers or payload.num_customers or 10
    now = datetime.now(timezone.utc)
    scan_docs = []
    disputes_injected = 0

    # Count existing scans to keep customer IDs unique across multiple bursts
    existing_count = await scan_events_col().count_documents({"vendor_id": payload.vendor_id})

    for i in range(num_customers):
        cust_num = existing_count + i + 1
        customer_id = f"sim_customer_{cust_num:04d}_{uuid.uuid4().hex[:6]}"
        customer_hash = _hash(customer_id)

        # Each customer scans between 3 and 5 times (all qualify as repeat customers)
        num_scans_for_customer = random.randint(3, 5)

        # Base visit starts between 10 and 60 days ago
        days_ago = random.randint(10, 60)
        base_hour = random.randint(8, 18)
        base_minute = random.randint(0, 59)
        first_visit = now - timedelta(days=days_ago)
        first_visit = first_visit.replace(hour=base_hour, minute=base_minute, second=0, microsecond=0)

        current_visit = first_visit
        for visit_idx in range(num_scans_for_customer):
            if visit_idx > 0:
                # Realistic gap: ~24 hours apart with subtle human variation (+/- 25 minutes)
                gap_hours = 24.0 + random.uniform(-0.4, 0.4)
                current_visit += timedelta(hours=gap_hours)
                # Ensure we don't exceed current time
                if current_visit > now:
                    current_visit = now - timedelta(minutes=random.randint(5, 60))

            amount = round(random.uniform(payload.min_amount, payload.max_amount), 2)
            is_dispute = random.random() < payload.dispute_rate
            if is_dispute:
                disputes_injected += 1

            scan_docs.append({
                "vendor_id": payload.vendor_id,
                "customer_hash": customer_hash,
                "timestamp": current_visit,
                "amount": amount,
            })

    # Bulk insert all generated scans
    if scan_docs:
        await scan_events_col().insert_many(scan_docs)

    # Increment vendor total_transactions and dispute_count
    await vendors_col().update_one(
        {"vendor_id": payload.vendor_id},
        {
            "$inc": {
                "total_transactions": len(scan_docs),
                "dispute_count": disputes_injected,
            }
        },
    )

    # Estimate updated metrics for the pipeline event stream
    estimated_repeat = (existing_count // 4) + num_customers
    estimated_visible = estimated_repeat >= 5
    estimated_tier = "TRUSTED" if estimated_repeat >= 50 else ("GROWING" if estimated_repeat >= 5 else "NEW")

    # Broadcast sequential pipeline stages for the live event stream
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "SCAN_RECEIVED",
        {
            "message": f"Simulated burst: {num_customers} repeat customers arrived ({len(scan_docs)} scans)",
            "customers": num_customers,
            "scans": len(scan_docs),
        },
    )
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "SCAN_STORED",
        {
            "message": f"{len(scan_docs)} scan events written to MongoDB scan_events",
            "collection": "scan_events",
        },
    )
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "AGGREGATION_UPDATED",
        {
            "message": f"Aggregated repeat customer groups ({len(scan_docs)} new scans)",
            "scans": len(scan_docs),
        },
    )
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "TRUST_CALCULATED",
        {
            "message": f"Trust Engine evaluating updated signals for tier '{estimated_tier}'",
            "tier": estimated_tier,
        },
    )
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "PRIVACY_CHECKED",
        {
            "message": (
                f"Privacy check: repeat_customers >= 5 (Badge visible)"
                if estimated_visible
                else f"K-anonymity floor active: repeat_customers < 5 (Badge hidden)"
            ),
            "badge_visible": estimated_visible,
        },
    )
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "BADGE_UPDATED",
        {
            "message": f"Committing trust badge: tier='{estimated_tier}', visible={estimated_visible}",
            "tier": estimated_tier,
            "badge_visible": estimated_visible,
        },
    )

    # Recalculate trust via Trust Engine and broadcast final TRUST_UPDATED
    badge = await recalculate_trust(payload.vendor_id)
    await ws_manager.broadcast(payload.vendor_id, badge.model_dump())

    # Fetch updated vendor_stats to report accurate response
    stats = await vendor_stats_col().find_one({"vendor_id": payload.vendor_id})
    repeat_customers_total = stats.get("repeat_customers", 0) if stats else 0
    trust_score = stats.get("trust_score", 0.0) if stats else 0.0
    tier = stats.get("trust_tier", "NEW") if stats else "NEW"
    badge_visible = stats.get("badge_visible", False) if stats else False

    # Broadcast 12-stage PROCESSING_DETAILS for developer/demo mode
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    burst_stages = [
        {
            "step": 1,
            "name": "Event received",
            "stage_id": "EVENT_RECEIVED",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Batch simulation received {num_customers} customer streams ({len(scan_docs)} QR scans) for vendor '{payload.vendor_id}'.",
            "details": {"customers_simulated": num_customers, "scans_count": len(scan_docs)},
        },
        {
            "step": 2,
            "name": "Event stored in MongoDB",
            "stage_id": "EVENT_STORED_MONGODB",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Appended {len(scan_docs)} offline scan records to MongoDB 'scan_events' collection.",
            "details": {"collection": "scan_events", "inserted_count": len(scan_docs)},
        },
        {
            "step": 3,
            "name": "Unique scanner aggregation",
            "stage_id": "UNIQUE_SCANNER_AGGREGATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"MongoDB grouped customer hashes: registered {stats.get('unique_scanners', num_customers) if stats else num_customers} distinct customer devices.",
            "details": {"unique_scanners": stats.get("unique_scanners", num_customers) if stats else num_customers},
        },
        {
            "step": 4,
            "name": "Repeat customer calculation",
            "stage_id": "REPEAT_CUSTOMER_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Identified {repeat_customers_total} unique repeat customers who scanned this vendor ≥ 3 times.",
            "details": {"repeat_customers": repeat_customers_total},
        },
        {
            "step": 5,
            "name": "Scan consistency calculation",
            "stage_id": "SCAN_CONSISTENCY_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Statistical engine calculated visit-interval regularity; consistency score = {stats.get('consistency_score', 95.0) if stats else 95.0:.1f}%.",
            "details": {"consistency_score": stats.get("consistency_score", 95.0) if stats else 95.0},
        },
        {
            "step": 6,
            "name": "Vendor tenure calculation",
            "stage_id": "VENDOR_TENURE_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Operational tenure: {stats.get('tenure_days', 450) if stats else 450} days active; tenure score = {stats.get('tenure_score', 100.0) if stats else 100.0:.1f}/100.",
            "details": {"tenure_days": stats.get("tenure_days", 450) if stats else 450},
        },
        {
            "step": 7,
            "name": "Dispute rate calculation",
            "stage_id": "DISPUTE_RATE_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Evaluated dispute ratio ({disputes_injected} disputes in batch, rate = {stats.get('dispute_rate', 0.0) if stats else 0.0:.2%}); dispute score = {stats.get('dispute_score', 100.0) if stats else 100.0:.1f}/100.",
            "details": {"disputes_injected": disputes_injected, "dispute_rate": stats.get("dispute_rate", 0.0) if stats else 0.0},
        },
        {
            "step": 8,
            "name": "Trust score calculation",
            "stage_id": "TRUST_SCORE_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Weighted composite trust calculated: composite trust score = {trust_score:.1f}/100.",
            "details": {"trust_score": trust_score},
        },
        {
            "step": 9,
            "name": "Trust tier calculation",
            "stage_id": "TRUST_TIER_CALCULATION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Threshold evaluation: {repeat_customers_total} repeat customers elevates vendor to tier: {tier}.",
            "details": {"tier": tier, "repeat_customers": repeat_customers_total},
        },
        {
            "step": 10,
            "name": "k-anonymity check",
            "stage_id": "K_ANONYMITY_CHECK",
            "status": "PASSED" if badge_visible else "MASKED",
            "timestamp": now_ts,
            "explanation": (
                f"Evaluated privacy floor (k ≥ 5): repeat_customers={repeat_customers_total}. "
                f"{'Privacy gate passed — vendor qualifies for public badge visibility.' if badge_visible else 'Privacy gate active — vendor badge hidden (k < 5).'}"
            ),
            "details": {"badge_visible": badge_visible, "repeat_customers": repeat_customers_total},
        },
        {
            "step": 11,
            "name": "Badge decision",
            "stage_id": "BADGE_DECISION",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Badge visibility set to {badge_visible}; updated trust metrics saved to MongoDB 'vendor_stats'.",
            "details": {"badge_visible": badge_visible, "tier": tier},
        },
        {
            "step": 12,
            "name": "WebSocket broadcast",
            "stage_id": "WEBSOCKET_BROADCAST",
            "status": "COMPLETED",
            "timestamp": now_ts,
            "explanation": f"Dispatched TRUST_UPDATED event with tier '{tier}' to connected clients without revealing customer identities.",
            "details": {"channel": f"/ws/vendor/{payload.vendor_id}"},
        },
    ]
    await ws_manager.broadcast_event(
        payload.vendor_id,
        "PROCESSING_DETAILS",
        {
            "vendor_id": payload.vendor_id,
            "timestamp": now_iso,
            "stages": burst_stages,
        },
    )

    return BurstSimulationResponse(
        status="ok",
        vendor_id=payload.vendor_id,
        customers_simulated=num_customers,
        scans_inserted=len(scan_docs),
        repeat_customers_total=repeat_customers_total,
        trust_score=trust_score,
        tier=tier,
        badge_visible=badge_visible,
        message=(
            f"Simulated {num_customers} repeat customers ({len(scan_docs)} total scans). "
            f"Vendor '{payload.vendor_id}' is now tier='{tier}' "
            f"({repeat_customers_total} repeat customers), badge_visible={badge_visible}."
        ),
    )


@router.post("/scan", response_model=ScanResponse, status_code=201)
async def simulate_single_scan(payload: SingleScanSimulationRequest):
    """
    Simulate a single live QR scan event for a vendor.
    Executes the complete 7-stage processing pipeline and broadcasts live over WebSocket.
    """
    await _ensure_vendor_exists(payload.vendor_id)

    # Auto-generate simulated customer ID if not supplied
    cust_id = payload.customer_id or f"walkin_cust_{uuid.uuid4().hex[:8]}"
    customer_hash = _hash(cust_id)
    now = datetime.now(timezone.utc)

    scan_id, badge, events, processing_details = await execute_scan_pipeline(
        vendor_id=payload.vendor_id,
        customer_hash=customer_hash,
        amount=payload.amount,
        scan_timestamp=now,
    )

    return ScanResponse(
        status="success",
        scan_id=scan_id,
        vendor_id=payload.vendor_id,
        timestamp=now,
        badge=badge,
        pipeline_events=events,
        processing_details=processing_details,
    )


@router.post("/reset", response_model=ResetResponse)
async def reset_simulation(payload: ResetRequest):
    """
    Reset vendor scan data to clean initial state.
    Broadcasts the hidden badge (NEW tier) to all active WebSocket clients.
    """
    if payload.vendor_id:
        vendor_id = payload.vendor_id
        await _ensure_vendor_exists(vendor_id)

        # Wipe scan events and stats
        await scan_events_col().delete_many({"vendor_id": vendor_id})
        await vendor_stats_col().delete_many({"vendor_id": vendor_id})
        await vendors_col().update_one(
            {"vendor_id": vendor_id},
            {"$set": {"dispute_count": 0, "total_transactions": 0}},
        )

        # Broadcast clean state (NEW tier, hidden badge)
        hidden_badge = {
            "vendor_id": vendor_id,
            "badge_visible": False,
            "trust_tier": "NEW",
            "tier_label": "NO TRUST BADGE",
            "tier_description": "Building history...",
            "total_scans_approx": None,
            "tenure_days": None,
        }
        await ws_manager.broadcast_event(
            vendor_id,
            "DEMO_RESET",
            {
                "message": f"Vendor '{vendor_id}' reset to clean initial baseline (0 scans, 0 repeat customers)",
                "vendor_id": vendor_id,
            },
        )
        await ws_manager.broadcast_trust_update(
            vendor_id=vendor_id,
            tier="NEW",
            badge_visible=False,
            trust_score=0.0,
            repeat_customers=0,
            message="Building history...",
            tier_label="NO TRUST BADGE",
            tier_description="Building history...",
            total_scans=0,
            consistency_score=0.0,
            dispute_rate=0.0,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        await ws_manager.broadcast(vendor_id, hidden_badge)

        return ResetResponse(
            status="ok",
            message=f"Reset vendor '{vendor_id}' to clean initial state (NEW tier, badge hidden).",
            vendors_affected=1,
            vendor_id=vendor_id,
        )
    else:
        # Reset all vendors
        res_scans = await scan_events_col().delete_many({})
        res_stats = await vendor_stats_col().delete_many({})
        await vendors_col().update_many(
            {},
            {"$set": {"dispute_count": 0, "total_transactions": 0}},
        )
        return ResetResponse(
            status="ok",
            message=f"Reset all vendors. Cleared {res_scans.deleted_count} scans and {res_stats.deleted_count} stats.",
            vendors_affected=res_stats.deleted_count,
        )
