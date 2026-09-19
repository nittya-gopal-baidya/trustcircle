"""
services/aggregator.py
----------------------
Aggregation Layer for TrustCircle.

Responsibility:
  - Executes MongoDB aggregation pipelines on the `scan_events` collection.
  - Groups transactions by customer hash to detect repeat regulars (>= 3 visits).
  - Extracts timestamp intervals to measure visit regularity.
  - Keeps all customer-level computation strictly inside the aggregation layer;
    never exposes raw customer data to the API or presentation tiers.

Architecture:
  Database (scan_events) -> [Aggregator] -> Trust Engine -> Privacy Gate -> WebSocket / API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.database import scan_events_col
from app.services.trust_engine import DEFAULT_CONFIG


async def aggregate_vendor_scans(vendor_id: str) -> Dict[str, Any]:
    """
    Executes a high-performance MongoDB aggregation pipeline for a vendor.

    Computes:
      - total_scans: total scan events recorded
      - unique_scanners: count of distinct customer hashes
      - repeat_customers: count of customer hashes with >= 3 scans
      - repeat_timestamps: timestamp arrays for repeat customers (for consistency CV)
      - avg_scan_interval_hours: average gap between repeat visits in hours
    """
    scans = scan_events_col()

    pipeline = [
        {"$match": {"vendor_id": vendor_id}},
        {
            "$group": {
                "_id": "$customer_hash",
                "scan_count": {"$sum": 1},
                "timestamps": {"$push": "$timestamp"},
            }
        },
    ]

    cursor = scans.aggregate(pipeline)
    customer_groups = await cursor.to_list(length=None)

    total_scans = sum(g["scan_count"] for g in customer_groups)
    unique_scanners = len(customer_groups)

    # Filter for repeat regulars: visit count >= repeat scan threshold (default 3)
    repeat_groups = [
        g for g in customer_groups
        if g["scan_count"] >= DEFAULT_CONFIG.REPEAT_SCAN_THRESHOLD
    ]
    repeat_customers = len(repeat_groups)
    repeat_timestamps = [g["timestamps"] for g in repeat_groups]

    # Calculate average visit interval in hours across all recurring visits
    all_intervals_hours: List[float] = []
    for g in customer_groups:
        ts_list = sorted(g["timestamps"])
        if len(ts_list) >= 2:
            for i in range(1, len(ts_list)):
                t1 = ts_list[i - 1]
                t2 = ts_list[i]
                if t1.tzinfo is None:
                    t1 = t1.replace(tzinfo=timezone.utc)
                if t2.tzinfo is None:
                    t2 = t2.replace(tzinfo=timezone.utc)
                diff = (t2 - t1).total_seconds() / 3600.0
                if diff >= 0:
                    all_intervals_hours.append(diff)

    avg_scan_interval_hours = (
        round(sum(all_intervals_hours) / len(all_intervals_hours), 2)
        if all_intervals_hours
        else 0.0
    )

    return {
        "vendor_id": vendor_id,
        "total_scans": total_scans,
        "unique_scanners": unique_scanners,
        "repeat_customers": repeat_customers,
        "repeat_timestamps": repeat_timestamps,
        "avg_scan_interval_hours": avg_scan_interval_hours,
    }
