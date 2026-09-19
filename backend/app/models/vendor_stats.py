"""
models/vendor_stats.py
----------------------
Aggregated trust state per vendor, stored in the `vendor_stats` collection.
This is computed by the Trust Engine and upserted after every scan.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

TrustTier = Literal["NEW", "GROWING", "TRUSTED", "COMMUNITY_FAVORITE"]


class VendorStatsDocument(BaseModel):
    """Shape of a document in the `vendor_stats` collection."""
    vendor_id: str

    # ── Raw aggregation signals ──────────────────────────────────────────────
    total_scans: int = 0
    unique_scanners: int = 0        # unique customer_hashes (all time)
    repeat_customers: int = 0       # customers with >= 3 scans (key trust signal)
    avg_scan_interval_hours: float = 0.0   # consistency signal
    tenure_days: int = 0            # days since first scan

    # ── Computed trust output ────────────────────────────────────────────────
    trust_score: float = 0.0        # 0–100 composite score
    trust_tier: TrustTier = "NEW"
    badge_visible: bool = False     # False when below k-anonymity floor (repeat_customers < 5)

    # ── Normalized individual signal scores (0–100) ──────────────────────────
    consistency_score: float = 0.0
    tenure_score: float = 0.0
    dispute_score: float = 0.0
    dispute_rate: float = 0.0

    last_updated: datetime = Field(default_factory=datetime.utcnow)
