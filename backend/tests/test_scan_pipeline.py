"""
tests/test_scan_pipeline.py
---------------------------
Integration tests for the complete QR scan processing pipeline.

Tests verify:
  1. POST /api/scans executes all 14 steps across the 7 stages:
     SCAN_RECEIVED -> SCAN_STORED -> AGGREGATION_UPDATED ->
     TRUST_CALCULATED -> PRIVACY_CHECK -> BADGE_UPDATED -> WEBSOCKET_BROADCAST
  2. customer_hash is strictly omitted from the API response
  3. No individual customer or transaction history is leaked
  4. Repeat customer detection (>= 3 scans per customer)
  5. K-anonymity privacy gating (hidden at 1..4 repeat customers, visible at 5)
  6. Persistence in MongoDB vendor_stats
  7. 404 response for unknown vendor_id
"""

import hashlib
import pytest
from httpx import ASGITransport, AsyncClient

from app.database import connect_db, close_db, scan_events_col, vendor_stats_col, vendors_col
from app.main import app


def _hash(customer_id: str) -> str:
    return hashlib.sha256(customer_id.encode()).hexdigest()


@pytest.fixture(autouse=True)
async def db_setup():
    await connect_db()
    # Seed vendor if not present
    await vendors_col().update_one(
        {"vendor_id": "vendor_test_chai"},
        {
            "$setOnInsert": {
                "vendor_id": "vendor_test_chai",
                "name": "Test Chai",
                "category": "Food & Beverage",
                "city": "Mumbai",
                "dispute_count": 0,
                "total_transactions": 0,
            }
        },
        upsert=True,
    )
    # Clean up test vendor scans and stats
    await scan_events_col().delete_many({"vendor_id": "vendor_test_chai"})
    await vendor_stats_col().delete_many({"vendor_id": "vendor_test_chai"})
    await vendors_col().update_one(
        {"vendor_id": "vendor_test_chai"},
        {"$set": {"dispute_count": 0, "total_transactions": 0}},
    )

    yield

    # Teardown clean
    await scan_events_col().delete_many({"vendor_id": "vendor_test_chai"})
    await vendor_stats_col().delete_many({"vendor_id": "vendor_test_chai"})
    await close_db()


@pytest.mark.anyio
async def test_complete_scan_pipeline_flow():
    """Verify the 7 stages and privacy guarantee of POST /api/scans."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cust_hash = _hash("cust_alpha")

        # Fire first scan
        resp = await client.post(
            "/api/scans",
            json={
                "vendor_id": "vendor_test_chai",
                "customer_hash": cust_hash,
                "amount": 50.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json()

        # 1. Basic response shape
        assert data["status"] == "success"
        assert data["vendor_id"] == "vendor_test_chai"
        assert "scan_id" in data
        assert "badge" in data
        assert "pipeline_events" in data

        # 2. Privacy verification: customer_hash must NEVER appear in the response
        raw_text = resp.text
        assert cust_hash not in raw_text, "Privacy violation: customer_hash leaked in response!"

        # 3. Verify all 7 stages were executed in exact order
        stages = [e["stage"] for e in data["pipeline_events"]]
        assert stages == [
            "SCAN_RECEIVED",
            "SCAN_STORED",
            "AGGREGATION_UPDATED",
            "TRUST_CALCULATED",
            "PRIVACY_CHECKED",
            "BADGE_UPDATED",
            "WEBSOCKET_BROADCAST",
        ]

        # 4. First scan is not a repeat customer yet (1 < 3 scans)
        agg_event = [e for e in data["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
        assert agg_event["details"]["total_scans"] == 1
        assert agg_event["details"]["unique_scanners"] == 1
        assert agg_event["details"]["repeat_customers"] == 0
        assert data["badge"]["badge_visible"] is False
        assert data["badge"]["trust_tier"] == "NEW"


@pytest.mark.anyio
async def test_repeat_customer_detection_and_k_anonymity():
    """Verify repeat customer threshold (>= 3 scans) and k-anonymity gate (>= 5 repeat customers)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Customer 1 scans 3 times -> becomes 1 repeat customer
        c1_hash = _hash("repeat_cust_1")
        await client.post("/api/scans", json={"vendor_id": "vendor_test_chai", "customer_hash": c1_hash, "amount": 20.0})
        await client.post("/api/scans", json={"vendor_id": "vendor_test_chai", "customer_hash": c1_hash, "amount": 20.0})
        r3 = await client.post("/api/scans", json={"vendor_id": "vendor_test_chai", "customer_hash": c1_hash, "amount": 20.0})

        r3_data = r3.json()
        agg_event = [e for e in r3_data["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
        assert agg_event["details"]["repeat_customers"] == 1
        # K-anonymity check: 1 < 5 -> badge must remain hidden
        assert r3_data["badge"]["badge_visible"] is False
        assert r3_data["badge"]["trust_tier"] == "NEW"

        # Step 2: Add 3 more repeat customers (customers 2, 3, 4 each scan 3 times)
        for i in [2, 3, 4]:
            ci_hash = _hash(f"repeat_cust_{i}")
            for _ in range(3):
                last_r = await client.post(
                    "/api/scans",
                    json={"vendor_id": "vendor_test_chai", "customer_hash": ci_hash, "amount": 20.0},
                )

        last_data = last_r.json()
        agg_event = [e for e in last_data["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
        # At 4 repeat customers, badge must STILL be hidden (k-anonymity floor is 5)
        assert agg_event["details"]["repeat_customers"] == 4
        assert last_data["badge"]["badge_visible"] is False
        assert last_data["badge"]["trust_tier"] == "NEW"

        # Step 3: Add 5th repeat customer (boundary crossing)
        c5_hash = _hash("repeat_cust_5")
        for _ in range(2):
            await client.post("/api/scans", json={"vendor_id": "vendor_test_chai", "customer_hash": c5_hash, "amount": 20.0})
        fifth_repeat_resp = await client.post(
            "/api/scans",
            json={"vendor_id": "vendor_test_chai", "customer_hash": c5_hash, "amount": 20.0},
        )
        fifth_data = fifth_repeat_resp.json()
        final_agg = [e for e in fifth_data["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
        assert final_agg["details"]["repeat_customers"] == 5

        # Badge becomes visible and transitions to GROWING tier!
        assert fifth_data["badge"]["badge_visible"] is True
        assert fifth_data["badge"]["trust_tier"] == "GROWING"
        assert fifth_data["badge"]["tier_label"] == "GROWING"

        # Step 4: Verify persistence in vendor_stats via GET /api/vendors/{id}/stats
        stats_resp = await client.get("/api/vendors/vendor_test_chai/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["repeat_customers"] == 5
        assert stats["badge_visible"] is True
        assert stats["trust_tier"] == "GROWING"
        assert stats["total_scans"] == 15  # 5 customers * 3 scans each


@pytest.mark.anyio
async def test_scan_invalid_vendor_returns_404():
    """Verify 404 response when scanning for a non-existent vendor."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/scans",
            json={
                "vendor_id": "non_existent_vendor_9999",
                "customer_hash": _hash("test_cust"),
                "amount": 10.0,
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
