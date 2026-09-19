"""
tests/test_seed.py
------------------
Verification suite for the TrustCircle Multi-Tier Seed System (python -m app.seed).

Verifies:
  1. All four demo tiers are properly generated:
     - NEW (< 5 repeat customers)
     - GROWING (5–49 repeat customers)
     - TRUSTED (50–499 repeat customers)
     - COMMUNITY_FAVORITE (500+ repeat customers)
  2. All four signals are calculated for every vendor:
     - unique repeat customers (scanned >= 3 times)
     - scan interval consistency (statistical regularity)
     - vendor tenure (days active vs 365 benchmark)
     - dispute/chargeback rate (disputes / total transactions)
  3. Strict k-anonymity privacy gating:
     - NEW tier vendor has badge_visible = False (k < 5 floor)
     - GROWING, TRUSTED, COMMUNITY_FAVORITE have badge_visible = True (k >= 5)
  4. Scans and stats persistence in the database
"""

import pytest
from app.database import (
    connect_db,
    close_db,
    vendors_col,
    vendor_stats_col,
    scan_events_col,
)
from app.seed import seed_all, DEMO_VENDOR_DEFINITIONS


@pytest.mark.anyio
async def test_seed_all_four_tiers():
    """Verify seed_all generates all 4 demo tiers with all 4 signals computed."""
    # Run seed in non-verbose mode for test
    summaries = await seed_all(verbose=False)

    assert len(summaries) == 4, f"Expected 4 vendor summaries, got {len(summaries)}"

    # Check definitions
    expected_tiers = ["NEW", "GROWING", "TRUSTED", "COMMUNITY_FAVORITE"]
    for idx, (summary, expected_tier) in enumerate(zip(summaries, expected_tiers)):
        assert summary["tier"] == expected_tier, (
            f"Vendor {summary['vendor_id']} tier mismatch: expected {expected_tier}, got {summary['tier']}"
        )

        # Signal 1: Unique repeat customers
        rc = summary["repeat_customers"]
        if expected_tier == "NEW":
            assert rc < 5, f"NEW tier vendor must have < 5 repeat customers, got {rc}"
            assert summary["badge_visible"] is False, "NEW tier vendor must have badge_visible=False"
        elif expected_tier == "GROWING":
            assert 5 <= rc <= 49, f"GROWING tier vendor must have 5-49 repeat customers, got {rc}"
            assert summary["badge_visible"] is True, "GROWING tier vendor must have badge_visible=True"
        elif expected_tier == "TRUSTED":
            assert 50 <= rc <= 499, f"TRUSTED tier vendor must have 50-499 repeat customers, got {rc}"
            assert summary["badge_visible"] is True, "TRUSTED tier vendor must have badge_visible=True"
        elif expected_tier == "COMMUNITY_FAVORITE":
            assert rc >= 500, f"COMMUNITY_FAVORITE tier vendor must have >= 500 repeat customers, got {rc}"
            assert summary["badge_visible"] is True, "COMMUNITY_FAVORITE must have badge_visible=True"

        # Signal 2: Scan interval consistency
        assert "consistency_score" in summary
        assert 0.0 <= summary["consistency_score"] <= 100.0

        # Signal 3: Vendor tenure
        assert "tenure_days" in summary
        assert "tenure_score" in summary
        assert summary["tenure_days"] > 0
        assert 0.0 <= summary["tenure_score"] <= 100.0

        # Signal 4: Dispute rate
        assert "dispute_rate" in summary
        assert "dispute_score" in summary
        assert 0.0 <= summary["dispute_rate"] <= 1.0
        assert 0.0 <= summary["dispute_score"] <= 100.0

        # Composite Trust Score
        assert "trust_score" in summary
        assert 0.0 <= summary["trust_score"] <= 100.0


@pytest.mark.anyio
async def test_database_records_after_seed():
    """Verify vendors, vendor_stats, and scan_events exist in MongoDB collections."""
    await connect_db()

    v_col = vendors_col()
    s_col = vendor_stats_col()
    scans = scan_events_col()

    for defn in DEMO_VENDOR_DEFINITIONS:
        # Vendor profile
        v_doc = await v_col.find_one({"vendor_id": defn.vendor_id})
        assert v_doc is not None, f"Vendor {defn.vendor_id} profile missing in MongoDB"
        assert v_doc["name"] == defn.name

        # Vendor stats
        s_doc = await s_col.find_one({"vendor_id": defn.vendor_id})
        assert s_doc is not None, f"Vendor stats for {defn.vendor_id} missing in MongoDB"
        assert s_doc["trust_tier"] == defn.tier_target
        assert s_doc["repeat_customers"] == defn.repeat_customers_count

        # Scan events
        count = await scans.count_documents({"vendor_id": defn.vendor_id})
        assert count > 0, f"Scan events for {defn.vendor_id} missing in MongoDB"
        assert count == s_doc["total_scans"]

    await close_db()
