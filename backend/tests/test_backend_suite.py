"""
tests/test_backend_suite.py
---------------------------
Comprehensive 20-Point Test Suite for the TrustCircle Backend.

Covers:
 1. Vendor creation
 2. Scan creation
 3. Repeat customer detection
 4. Customer with 1 scan is not repeat
 5. Customer with 2 scans is not repeat
 6. Customer with 3 scans becomes repeat
 7. Unique repeat customer calculation
 8. Multiple scans from same customer count as one repeat customer
 9. k-anonymity: 4 repeat customers -> badge hidden; 5 repeat customers -> badge can appear
10. NEW tier (< 5 repeat customers)
11. GROWING tier (5-49 repeat customers)
12. TRUSTED tier (50-499 repeat customers)
13. COMMUNITY_FAVORITE tier (500+ repeat customers)
14. Dispute rate calculation
15. Scan consistency calculation
16. Vendor tenure calculation
17. Simulation burst
18. Reset demo
19. API response privacy
20. WebSocket event generation
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.database import (
    close_db,
    connect_db,
    scan_events_col,
    vendor_stats_col,
    vendors_col,
)
from app.main import app
from app.services.trust_engine import (
    DEFAULT_CONFIG,
    TrustEngine,
    TrustTier,
    assign_tier,
    calculate_dispute_score,
    calculate_repeat_score,
    calculate_scan_consistency,
    calculate_tenure_score,
)

SUITE_VENDOR = "suite_test_vendor"


def _sha256(text: str) -> str:
    """Helper to compute deterministic SHA-256 hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _reset_vendor(vendor_id: str = SUITE_VENDOR):
    """Ensure clean test vendor state in database."""
    await connect_db()
    await vendors_col().update_one(
        {"vendor_id": vendor_id},
        {
            "$set": {
                "vendor_id": vendor_id,
                "name": "Suite Test Vendor Corner",
                "category": "Food & Beverage",
                "city": "Bengaluru",
                "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
                "dispute_count": 0,
                "total_transactions": 0,
            }
        },
        upsert=True,
    )
    await scan_events_col().delete_many({"vendor_id": vendor_id})
    await vendor_stats_col().delete_many({"vendor_id": vendor_id})


# ── TEST 1: Vendor creation ──────────────────────────────────────────────────
@pytest.mark.anyio
async def test_01_vendor_creation():
    """1. Vendor creation: Verify vendor is created and retrieved with correct schema."""
    await _reset_vendor()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/vendors/{SUITE_VENDOR}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vendor_id"] == SUITE_VENDOR
        assert data["name"] == "Suite Test Vendor Corner"
        assert data["city"] == "Bengaluru"


# ── TEST 2: Scan creation ────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_02_scan_creation():
    """2. Scan creation: POST /api/scans persists scan event and increments transactions."""
    await _reset_vendor()
    cust_hash = _sha256("test_customer_001")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/scans",
            json={
                "vendor_id": SUITE_VENDOR,
                "customer_hash": cust_hash,
                "amount": 45.0,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "success"
        assert body["vendor_id"] == SUITE_VENDOR
        assert "scan_id" in body

    # Verify event stored in MongoDB scan_events
    stored_scan = await scan_events_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stored_scan is not None
    assert stored_scan["customer_hash"] == cust_hash
    assert stored_scan["amount"] == 45.0

    # Verify vendor total_transactions incremented
    vendor = await vendors_col().find_one({"vendor_id": SUITE_VENDOR})
    assert vendor["total_transactions"] == 1


# ── TEST 3: Repeat customer detection ────────────────────────────────────────
@pytest.mark.anyio
async def test_03_repeat_customer_detection():
    """3. Repeat customer detection: Detects repeat customers when visit threshold (>=3) is met."""
    await _reset_vendor()
    cust_hash = _sha256("loyal_shopper")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            res = await client.post(
                "/api/scans",
                json={
                    "vendor_id": SUITE_VENDOR,
                    "customer_hash": cust_hash,
                    "amount": 20.0,
                },
            )
            assert res.status_code == 201

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats is not None
    assert stats["repeat_customers"] == 1
    assert stats["unique_scanners"] == 1
    assert stats["total_scans"] == 3


# ── TEST 4: Customer with 1 scan is not repeat ──────────────────────────────
@pytest.mark.anyio
async def test_04_customer_with_1_scan_is_not_repeat():
    """4. Customer with 1 scan is NOT a repeat customer."""
    await _reset_vendor()
    cust_hash = _sha256("one_time_visitor")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/scans",
            json={
                "vendor_id": SUITE_VENDOR,
                "customer_hash": cust_hash,
                "amount": 10.0,
            },
        )
        assert resp.status_code == 201

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats["repeat_customers"] == 0
    assert stats["total_scans"] == 1


# ── TEST 5: Customer with 2 scans is not repeat ──────────────────────────────
@pytest.mark.anyio
async def test_05_customer_with_2_scans_is_not_repeat():
    """5. Customer with 2 scans is still NOT a repeat customer (threshold is >= 3)."""
    await _reset_vendor()
    cust_hash = _sha256("two_time_visitor")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            resp = await client.post(
                "/api/scans",
                json={
                    "vendor_id": SUITE_VENDOR,
                    "customer_hash": cust_hash,
                    "amount": 15.0,
                },
            )
            assert resp.status_code == 201

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats["repeat_customers"] == 0
    assert stats["total_scans"] == 2


# ── TEST 6: Customer with 3 scans becomes repeat ─────────────────────────────
@pytest.mark.anyio
async def test_06_customer_with_3_scans_becomes_repeat():
    """6. Customer with 3 scans transitions to repeat customer."""
    await _reset_vendor()
    cust_hash = _sha256("regular_visitor")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1st scan
        await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_hash, "amount": 12.0})
        stats_1 = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
        assert stats_1["repeat_customers"] == 0

        # 2nd scan
        await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_hash, "amount": 12.0})
        stats_2 = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
        assert stats_2["repeat_customers"] == 0

        # 3rd scan -> triggers repeat customer
        await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_hash, "amount": 12.0})
        stats_3 = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
        assert stats_3["repeat_customers"] == 1


# ── TEST 7: Unique repeat customer calculation ───────────────────────────────
@pytest.mark.anyio
async def test_07_unique_repeat_customer_calculation():
    """7. Unique repeat customer calculation: 2 distinct customers with >= 3 scans = 2 repeat customers."""
    await _reset_vendor()
    cust_a = _sha256("customer_alpha")
    cust_b = _sha256("customer_beta")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_a, "amount": 10.0})
        for _ in range(3):
            await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_b, "amount": 15.0})

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats["repeat_customers"] == 2
    assert stats["unique_scanners"] == 2
    assert stats["total_scans"] == 6


# ── TEST 8: Multiple scans from same customer count as one repeat customer ──
@pytest.mark.anyio
async def test_08_multiple_scans_from_same_customer_count_as_one_repeat():
    """8. Multiple scans from the same customer (e.g. 10 scans) count as exactly ONE repeat customer."""
    await _reset_vendor()
    cust_heavy = _sha256("heavy_user")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(10):
            await client.post("/api/scans", json={"vendor_id": SUITE_VENDOR, "customer_hash": cust_heavy, "amount": 25.0})

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats["repeat_customers"] == 1
    assert stats["unique_scanners"] == 1
    assert stats["total_scans"] == 10


# ── TEST 9: k-anonymity: 4 repeat customers -> hidden; 5 -> visible ──────────
def test_09_k_anonymity_floor():
    """9. k-anonymity: 4 repeat customers -> badge hidden; 5 repeat customers -> badge can appear."""
    # 4 repeat customers: below k=5 floor
    res_4 = TrustEngine.calculate(repeat_customers=4, consistency_score=95.0, tenure_score=80.0, dispute_score=100.0)
    assert res_4["badge_visible"] is False
    assert res_4["tier"] == "NEW"

    # 5 repeat customers: meets k=5 floor
    res_5 = TrustEngine.calculate(repeat_customers=5, consistency_score=95.0, tenure_score=80.0, dispute_score=100.0)
    assert res_5["badge_visible"] is True
    assert res_5["tier"] == "GROWING"


# ── TEST 10: NEW tier ────────────────────────────────────────────────────────
def test_10_tier_new():
    """10. NEW tier: Asserts vendor with fewer than 5 repeat customers is categorized as NEW."""
    for count in [0, 1, 2, 3, 4]:
        tier = assign_tier(count)
        assert tier == "NEW"

    res = TrustEngine.calculate(repeat_customers=2)
    assert res["tier"] == "NEW"
    assert res["badge_visible"] is False


# ── TEST 11: GROWING tier ────────────────────────────────────────────────────
def test_11_tier_growing():
    """11. GROWING tier: Asserts vendor with 5 to 49 repeat customers is categorized as GROWING."""
    for count in [5, 20, 49]:
        tier = assign_tier(count)
        assert tier == "GROWING"

    res = TrustEngine.calculate(repeat_customers=25)
    assert res["tier"] == "GROWING"
    assert res["badge_visible"] is True


# ── TEST 12: TRUSTED tier ────────────────────────────────────────────────────
def test_12_tier_trusted():
    """12. TRUSTED tier: Asserts vendor with 50 to 499 repeat customers is categorized as TRUSTED."""
    for count in [50, 150, 499]:
        tier = assign_tier(count)
        assert tier == "TRUSTED"

    res = TrustEngine.calculate(repeat_customers=120)
    assert res["tier"] == "TRUSTED"
    assert res["badge_visible"] is True


# ── TEST 13: COMMUNITY_FAVORITE tier ─────────────────────────────────────────
def test_13_tier_community_favorite():
    """13. COMMUNITY_FAVORITE tier: Asserts vendor with 500+ repeat customers is COMMUNITY_FAVORITE."""
    for count in [500, 750, 2000]:
        tier = assign_tier(count)
        assert tier == "COMMUNITY_FAVORITE"

    res = TrustEngine.calculate(repeat_customers=600)
    assert res["tier"] == "COMMUNITY_FAVORITE"
    assert res["badge_visible"] is True


# ── TEST 14: Dispute rate calculation ────────────────────────────────────────
def test_14_dispute_rate_calculation():
    """14. Dispute rate calculation: 0 disputes = 100 score; higher dispute rate incurs proportional penalty."""
    rate_0, score_0 = calculate_dispute_score(dispute_count=0, total_transactions=100)
    assert rate_0 == 0.0
    assert score_0 == 100.0

    rate_1, score_1 = calculate_dispute_score(dispute_count=1, total_transactions=100)
    assert rate_1 == 0.01
    assert score_1 == 80.0

    rate_5, score_5 = calculate_dispute_score(dispute_count=5, total_transactions=100)
    assert rate_5 == 0.05
    assert score_5 == 0.0


# ── TEST 15: Scan consistency calculation ────────────────────────────────────
def test_15_scan_consistency_calculation():
    """15. Scan consistency calculation: Habitual regular intervals score higher than erratic bursts."""
    regular_intervals = [24.0, 24.1, 23.9, 24.0, 24.0]
    high_score = calculate_scan_consistency(intervals_hours=regular_intervals)
    assert high_score >= 95.0

    erratic_intervals = [1.0, 100.0, 2.0, 80.0, 0.5]
    low_score = calculate_scan_consistency(intervals_hours=erratic_intervals)
    assert low_score < 40.0


# ── TEST 16: Vendor tenure calculation ───────────────────────────────────────
def test_16_vendor_tenure_calculation():
    """16. Vendor tenure calculation: Matures from 0 to 100 normalized over 365 benchmark days."""
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # 365 days ago -> 100.0
    created_365 = now - timedelta(days=365)
    days_365, score_365 = calculate_tenure_score(created_365, current_date=now)
    assert days_365 == 365
    assert score_365 == 100.0

    # 182.5 days ago -> ~50.0
    created_182 = now - timedelta(days=182)
    days_182, score_182 = calculate_tenure_score(created_182, current_date=now)
    assert days_182 == 182
    assert 49.0 <= score_182 <= 51.0

    # 0 days ago -> 0.0
    days_0, score_0 = calculate_tenure_score(now, current_date=now)
    assert days_0 == 0
    assert score_0 == 0.0


# ── TEST 17: Simulation burst ────────────────────────────────────────────────
@pytest.mark.anyio
async def test_17_simulation_burst():
    """17. Simulation burst: Generates repeat customer batch and advances tier."""
    await _reset_vendor()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/simulation/burst",
            json={"vendor_id": SUITE_VENDOR, "customers": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["customers_simulated"] == 5
        assert data["repeat_customers_total"] == 5
        assert data["tier"] == "GROWING"
        assert data["badge_visible"] is True

    stats = await vendor_stats_col().find_one({"vendor_id": SUITE_VENDOR})
    assert stats["repeat_customers"] == 5
    assert stats["trust_tier"] == "GROWING"
    assert stats["badge_visible"] is True


# ── TEST 18: Reset demo ──────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_18_reset_demo():
    """18. Reset demo: Clears scans, returns vendor to clean NEW tier, and hides badge."""
    await _reset_vendor()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add some scans first
        await client.post(
            "/api/simulation/burst",
            json={"vendor_id": SUITE_VENDOR, "customers": 5},
        )
        # Now reset
        reset_resp = await client.post(
            "/api/simulation/reset",
            json={"vendor_id": SUITE_VENDOR},
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "ok"

        # Check vendor stats via API
        stats_resp = await client.get(f"/api/vendors/{SUITE_VENDOR}/stats")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["repeat_customers"] == 0
        assert stats_data["total_scans"] == 0
        assert stats_data["trust_tier"] == "NEW"
        assert stats_data["badge_visible"] is False


# ── TEST 19: API response privacy ────────────────────────────────────────────
@pytest.mark.anyio
async def test_19_api_response_privacy():
    """19. API response privacy: customer_hash and raw transactions are never leaked in API responses."""
    await _reset_vendor()
    secret_hash = _sha256("private_customer_account_443")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Post a scan
        scan_res = await client.post(
            "/api/scans",
            json={
                "vendor_id": SUITE_VENDOR,
                "customer_hash": secret_hash,
                "amount": 50.0,
            },
        )
        assert scan_res.status_code == 201
        scan_text = scan_res.text
        assert secret_hash not in scan_text  # Hash strictly omitted from response
        assert "customer_hash" not in scan_res.json()

        # 2. Check public vendor endpoint
        vendor_res = await client.get(f"/api/vendors/{SUITE_VENDOR}")
        assert vendor_res.status_code == 200
        assert secret_hash not in vendor_res.text

        # 3. Check customer-facing badge endpoint
        badge_res = await client.get(f"/api/vendors/{SUITE_VENDOR}/badge")
        assert badge_res.status_code == 200
        badge_data = badge_res.json()
        assert badge_data["badge_visible"] is False
        assert badge_data["trust_tier"] == "NEW"
        assert badge_data.get("total_scans_approx") is None


# ── TEST 20: WebSocket event generation ──────────────────────────────────────
def test_20_websocket_event_generation():
    """20. WebSocket event generation: Broadcasts real-time events without customer PII."""
    cust_hash = _sha256("ws_demo_customer")

    with TestClient(app) as client:
        # Reset vendor to clean state
        client.post("/api/simulation/reset", json={"vendor_id": "sharma_chai_001"})

        with client.websocket_connect("/ws/vendor/sharma_chai_001") as ws:
            # First message is initial TRUST_UPDATED state
            initial_msg = ws.receive_json()
            assert initial_msg["event"] == "TRUST_UPDATED"
            assert initial_msg["vendor_id"] == "sharma_chai_001"

            # Post a scan while connected
            scan_resp = client.post(
                "/api/scans",
                json={
                    "vendor_id": "sharma_chai_001",
                    "customer_hash": cust_hash,
                    "amount": 25.0,
                },
            )
            assert scan_resp.status_code == 201

            # Read broadcast frames from WebSocket
            received_events = []
            for _ in range(8):
                frame = ws.receive_json()
                received_events.append(frame.get("event"))
                frame_text = json.dumps(frame)
                assert cust_hash not in frame_text

            assert "SCAN_RECEIVED" in received_events
            assert "SCAN_STORED" in received_events
            assert "AGGREGATION_UPDATED" in received_events
            assert "TRUST_CALCULATED" in received_events
            assert "PRIVACY_CHECKED" in received_events
            assert "BADGE_UPDATED" in received_events
            assert "TRUST_UPDATED" in received_events
