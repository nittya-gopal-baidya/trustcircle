"""
schemas/vendor.py
-----------------
API request/response shapes for vendor endpoints.
These are deliberately different from VendorDocument —
they never expose internal fields like customer_hash.
"""

from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from app.models.vendor_stats import TrustTier


# ── Response: GET /api/vendors/{vendor_id} ───────────────────────────────────

class VendorResponse(BaseModel):
    vendor_id: str
    name: str
    category: str
    city: str
    created_at: datetime
    dispute_count: int
    total_transactions: int


# ── Response: GET /api/vendors/{vendor_id}/stats (full stats for judges/demo) ─

class VendorStatsResponse(BaseModel):
    vendor_id: str
    total_scans: int
    unique_scanners: int
    repeat_customers: int           # internal count — only shown on /stats endpoint
    avg_scan_interval_hours: float
    tenure_days: int
    trust_score: float
    trust_tier: TrustTier
    badge_visible: bool
    consistency_score: Optional[float] = None
    tenure_score: Optional[float] = None
    dispute_score: Optional[float] = None
    dispute_rate: Optional[float] = 0.0
    last_updated: datetime


# ── Response: Badge payload pushed via WebSocket and badge API ───────────────

class BadgePayload(BaseModel):
    """
    Customer-facing trust badge payload.
    Privacy rules applied:
      - repeat_customers count is NEVER included if badge_visible is False
      - customer_hash is NEVER included
    """
    vendor_id: str
    badge_visible: bool
    trust_tier: TrustTier
    tier_label: str
    tier_description: Optional[str] = None
    total_scans_approx: Optional[str] = None   # bucketed string e.g. "80+"
    tenure_days: Optional[int] = None
