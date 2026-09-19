"""
routes/vendors.py
-----------------
GET /api/vendors/{vendor_id}         → public vendor profile
GET /api/vendors/{vendor_id}/stats   → full trust stats (internal/judge view)
GET /api/vendors                     → list all vendors (for demo dropdown)
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.database import vendors_col, vendor_stats_col
from app.schemas.vendor import VendorResponse, VendorStatsResponse, BadgePayload
from app.services.trust_engine import TIER_META, _bucket_scans

router = APIRouter(prefix="/api/vendors", tags=["Vendors"])


@router.get("", response_model=list[VendorResponse])
async def list_vendors():
    """Return all seeded vendors for the frontend demo dropdown."""
    cursor = vendors_col().find({}, {"_id": 0})
    vendors = await cursor.to_list(length=100)
    return vendors


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(vendor_id: str):
    """
    Public vendor profile.
    Does NOT include trust/badge data — that comes from /stats or WebSocket.
    """
    doc = await vendors_col().find_one({"vendor_id": vendor_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
    return doc


@router.get("/{vendor_id}/stats", response_model=VendorStatsResponse)
async def get_vendor_stats(vendor_id: str):
    """
    Full aggregated trust stats — intended for judges/internal demo.
    Exposes repeat_customers count directly (not safe for public).
    If no scans exist yet, returns clean default stats (tier=NEW, 0 scans).
    """
    doc = await vendor_stats_col().find_one({"vendor_id": vendor_id}, {"_id": 0})
    if not doc:
        vendor = await vendors_col().find_one({"vendor_id": vendor_id})
        if not vendor:
            if vendor_id == "sharma_chai_001":
                from app.routes.simulation import _ensure_vendor_exists
                vendor = await _ensure_vendor_exists(vendor_id)
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Vendor '{vendor_id}' not found."
                )

        now = datetime.now(timezone.utc)
        created_at = vendor.get("created_at", now)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        tenure_days = max(0, (now - created_at).days)

        return VendorStatsResponse(
            vendor_id=vendor_id,
            total_scans=0,
            unique_scanners=0,
            repeat_customers=0,
            avg_scan_interval_hours=0.0,
            tenure_days=tenure_days,
            trust_score=0.0,
            trust_tier="NEW",
            badge_visible=False,
            consistency_score=0.0,
            tenure_score=round(min(100.0, (tenure_days / 365.0) * 100.0), 1),
            dispute_score=100.0,
            dispute_rate=0.0,
            last_updated=now,
        )
    return doc


@router.get("/{vendor_id}/badge", response_model=BadgePayload)
async def get_badge(vendor_id: str):
    """
    Customer-facing badge endpoint — privacy-safe.
    Mirrors the WebSocket payload. Useful for initial page load before WS connects.
    """
    doc = await vendor_stats_col().find_one({"vendor_id": vendor_id}, {"_id": 0})

    if not doc:
        # Vendor exists but has no scans yet → return hidden badge
        vendor = await vendors_col().find_one({"vendor_id": vendor_id})
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
        return BadgePayload(
            vendor_id=vendor_id,
            badge_visible=False,
            trust_tier="NEW",
            tier_label="New Vendor",
        )

    trust_tier = doc["trust_tier"]
    badge_visible = doc["badge_visible"]
    meta = TIER_META[trust_tier]

    return BadgePayload(
        vendor_id=vendor_id,
        badge_visible=badge_visible,
        trust_tier=trust_tier,
        tier_label=meta["label"],
        tier_description=meta["description"] if badge_visible else None,
        total_scans_approx=_bucket_scans(doc["total_scans"]) if badge_visible else None,
        tenure_days=doc["tenure_days"] if badge_visible else None,
    )
