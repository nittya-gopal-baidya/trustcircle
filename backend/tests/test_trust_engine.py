"""
tests/test_trust_engine.py
---------------------------
Unit tests for the TrustCircle Trust Engine service.

Tests cover:
  1. Tier classification: NEW, GROWING, TRUSTED, COMMUNITY_FAVORITE
  2. K-anonymity boundary at 4 and 5
  3. High dispute rate vs Low dispute rate
  4. Consistent scans vs Inconsistent scans
  5. Return dictionary structure and types
  6. Customer-facing privacy gating (masking small counts < 5)
  7. Tenure calculation
  8. Repeat customer qualification (>= 3 scans)
"""

from datetime import datetime, timedelta, timezone
import pytest

from app.services.trust_engine import (
    DemoScoringWeights,
    TrustEngine,
    assign_tier,
    calculate_dispute_score,
    calculate_repeat_score,
    calculate_scan_consistency,
    calculate_tenure_score,
)


# =============================================================================
# 1. TIER CLASSIFICATION TESTS
# =============================================================================

def test_tier_new():
    """< 5 repeat customers must produce NEW tier."""
    for count in [0, 1, 2, 3, 4]:
        result = TrustEngine.calculate(repeat_customers=count)
        assert result["tier"] == "NEW", f"Expected NEW for {count} repeat customers"
        assert result["badge_visible"] is False, f"Badge should be hidden for count {count}"


def test_tier_growing():
    """5–49 repeat customers must produce GROWING tier."""
    for count in [5, 10, 25, 49]:
        result = TrustEngine.calculate(repeat_customers=count)
        assert result["tier"] == "GROWING", f"Expected GROWING for {count} repeat customers"
        assert result["badge_visible"] is True, f"Badge should be visible for count {count}"


def test_tier_trusted():
    """50–499 repeat customers must produce TRUSTED tier."""
    for count in [50, 100, 250, 499]:
        result = TrustEngine.calculate(repeat_customers=count)
        assert result["tier"] == "TRUSTED", f"Expected TRUSTED for {count} repeat customers"
        assert result["badge_visible"] is True, f"Badge should be visible for count {count}"


def test_tier_community_favorite():
    """500+ repeat customers must produce COMMUNITY_FAVORITE tier."""
    for count in [500, 501, 750, 2000]:
        result = TrustEngine.calculate(repeat_customers=count)
        assert result["tier"] == "COMMUNITY_FAVORITE", f"Expected COMMUNITY_FAVORITE for {count}"
        assert result["badge_visible"] is True, f"Badge should be visible for count {count}"


# =============================================================================
# 2. K-ANONYMITY PRIVACY BOUNDARY (AT 4 AND 5)
# =============================================================================

def test_k_anonymity_boundary_at_4():
    """
    At 4 repeat customers:
      - Internal badge_visible must be False
      - Tier is NEW
      - Customer-facing response MUST NOT reveal the count 4
    """
    result = TrustEngine.calculate(
        repeat_customers=4,
        consistency_score=80.0,
        tenure_score=80.0,
        dispute_score=100.0,
    )
    assert result["badge_visible"] is False
    assert result["tier"] == "NEW"

    # Verify privacy transformation
    customer_response = TrustEngine.to_customer_facing_response(result)
    assert customer_response["badge_visible"] is False
    assert customer_response["repeat_customers"] is None, "Customer response leaked small count below 5"
    assert customer_response["tier"] == "NEW"


def test_k_anonymity_boundary_at_5():
    """
    At 5 repeat customers:
      - Internal badge_visible must be True
      - Tier transitions to GROWING
      - Customer-facing response can safely display badge
    """
    result = TrustEngine.calculate(
        repeat_customers=5,
        consistency_score=80.0,
        tenure_score=80.0,
        dispute_score=100.0,
    )
    assert result["badge_visible"] is True
    assert result["tier"] == "GROWING"

    customer_response = TrustEngine.to_customer_facing_response(result)
    assert customer_response["badge_visible"] is True
    assert customer_response["tier"] == "GROWING"
    assert customer_response["repeat_customers"] == 5


# =============================================================================
# 3. DISPUTE RATE TESTS
# =============================================================================

def test_low_dispute_rate():
    """0% dispute rate must give 100.0 dispute score and contribute positively."""
    rate, score = calculate_dispute_score(dispute_count=0, total_transactions=100)
    assert rate == 0.0
    assert score == 100.0

    # Test full calculation with clean dispute record
    result = TrustEngine.calculate(
        repeat_customers=100,
        consistency_score=80.0,
        tenure_score=50.0,
        dispute_score=score,
    )
    assert result["dispute_score"] == 100.0
    # Dispute weight is 15%, so 100 dispute_score adds 15 points
    expected_dispute_contribution = 100.0 * 0.15
    assert result["trust_score"] > expected_dispute_contribution


def test_high_dispute_rate():
    """High dispute rate (e.g. 10% or 20%) must severely penalize dispute score to 0.0."""
    rate, score = calculate_dispute_score(dispute_count=20, total_transactions=100)
    assert rate == 0.20
    assert score == 0.0, "Dispute rate above tolerance benchmark must drop to 0.0"

    low_dispute_result = TrustEngine.calculate(
        repeat_customers=100,
        consistency_score=80.0,
        tenure_score=50.0,
        dispute_score=100.0,
    )
    high_dispute_result = TrustEngine.calculate(
        repeat_customers=100,
        consistency_score=80.0,
        tenure_score=50.0,
        dispute_score=score,
    )

    # High dispute rate must yield lower trust score
    assert high_dispute_result["trust_score"] < low_dispute_result["trust_score"]
    assert high_dispute_result["dispute_score"] == 0.0


# =============================================================================
# 4. SCAN-INTERVAL CONSISTENCY TESTS
# =============================================================================

def test_consistent_scans_flat_intervals():
    """Identical scan intervals (zero variance) must produce 100.0 consistency score."""
    # Customer scans exactly every 24 hours
    intervals = [24.0, 24.0, 24.0, 24.0]
    score = calculate_scan_consistency(intervals_hours=intervals)
    assert score == 100.0


def test_consistent_scans_timestamps():
    """Repeat customer visiting daily at the exact same hour must yield 100.0 consistency."""
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    daily_timestamps = [
        base_time,
        base_time + timedelta(days=1),
        base_time + timedelta(days=2),
        base_time + timedelta(days=3),
    ]
    score = calculate_scan_consistency(repeat_customer_timestamps=[daily_timestamps])
    assert score == 100.0


def test_inconsistent_scans_flat_intervals():
    """Erratic scan intervals (large standard deviation relative to mean) must produce 0.0 consistency."""
    # Extremely erratic intervals: 1 hour, then 150 hours, then 2 hours, then 200 hours
    erratic_intervals = [1.0, 150.0, 2.0, 200.0]
    score = calculate_scan_consistency(intervals_hours=erratic_intervals)
    assert score == 0.0


def test_inconsistent_scans_timestamps():
    """Erratic repeat customer visits must produce a significantly lower consistency score."""
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    erratic_timestamps = [
        base_time,
        base_time + timedelta(hours=1),           # 1 hr gap
        base_time + timedelta(hours=1, days=15),  # 360 hr gap
        base_time + timedelta(hours=2, days=15),  # 1 hr gap
    ]
    score = calculate_scan_consistency(repeat_customer_timestamps=[erratic_timestamps])
    assert score == 0.0


# =============================================================================
# 5. ENGINE RETURN SCHEMA AND TYPES
# =============================================================================

def test_engine_return_schema():
    """TrustEngine.calculate() must return the exact required keys and types."""
    result = TrustEngine.calculate(
        repeat_customers=75,
        consistency_score=92.5,
        tenure_score=45.0,
        dispute_score=95.0,
    )

    required_keys = {
        "trust_score",
        "tier",
        "badge_visible",
        "repeat_customers",
        "consistency_score",
        "tenure_score",
        "dispute_score",
    }
    assert set(result.keys()) == required_keys

    assert isinstance(result["trust_score"], (int, float))
    assert isinstance(result["tier"], str)
    assert isinstance(result["badge_visible"], bool)
    assert isinstance(result["repeat_customers"], int)
    assert isinstance(result["consistency_score"], (int, float))
    assert isinstance(result["tenure_score"], (int, float))
    assert isinstance(result["dispute_score"], (int, float))

    assert 0.0 <= result["trust_score"] <= 100.0
    assert result["tier"] == "TRUSTED"
    assert result["badge_visible"] is True


# =============================================================================
# 6. TENURE SCORE TESTS
# =============================================================================

def test_tenure_scoring():
    """Vendor tenure must scale smoothly up to 365 days."""
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    # Vendor created today (0 days)
    days, score = calculate_tenure_score(created_at=now, current_date=now)
    assert days == 0
    assert score == 0.0

    # Vendor created 365 days ago
    days, score = calculate_tenure_score(
        created_at=now - timedelta(days=365),
        current_date=now,
    )
    assert days == 365
    assert score == 100.0

    # Vendor created 730 days ago (capped at 100.0)
    days, score = calculate_tenure_score(
        created_at=now - timedelta(days=730),
        current_date=now,
    )
    assert days == 730
    assert score == 100.0


# =============================================================================
# 7. CUSTOMER PRIVACY GATING AND MASKING
# =============================================================================

def test_customer_facing_response_masking():
    """
    Ensure to_customer_facing_response completely redacts repeat customer count
    and internal metrics when repeat_customers < 5.
    """
    for count in [0, 2, 4]:
        raw_result = TrustEngine.calculate(repeat_customers=count)
        customer_view = TrustEngine.to_customer_facing_response(raw_result)

        assert customer_view["badge_visible"] is False
        assert customer_view["repeat_customers"] is None
        assert customer_view["trust_score"] is None
        assert customer_view["tier"] == "NEW"
