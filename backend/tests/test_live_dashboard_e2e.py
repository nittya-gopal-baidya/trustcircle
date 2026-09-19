"""
tests/test_live_dashboard_e2e.py
---------------------------------
End-to-End integration test for TrustCircle Live Processing Dashboard.
Verifies:
  1. WebSocket connection to ws://localhost:8000/ws/vendor/sharma_chai_001
  2. Reset demo: POST /api/simulation/reset -> DEMO_RESET & TRUST_UPDATED (NEW tier)
  3. Single scan simulation: POST /api/simulation/scan -> 6 stages streamed live:
       - SCAN_RECEIVED
       - SCAN_STORED
       - AGGREGATION_UPDATED
       - TRUST_CALCULATED
       - PRIVACY_CHECKED
       - BADGE_UPDATED
  4. +5 Repeat Customers: POST /api/simulation/burst (5) -> unlocks GROWING tier (K >= 5)
  5. +50 Repeat Customers: POST /api/simulation/burst (50) -> unlocks TRUSTED tier
  6. GET /api/vendors/sharma_chai_001/stats returns all 8 required dashboard metrics:
       - Trust Tier
       - Trust Score
       - Repeat Customers
       - Total Scans
       - Scan Consistency
       - Vendor Tenure
       - Dispute Rate
       - Last Updated
"""

import asyncio
import json
import pytest
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient
from app.main import app


@pytest.mark.anyio
async def test_live_processing_dashboard_websocket_and_apis():
    """Verify live event stream and metrics across simulation actions."""
    # Use TestClient for WebSocket support with ASGI
    with TestClient(app) as test_client:
        # 1. Connect to vendor WebSocket
        with test_client.websocket_connect("/ws/vendor/sharma_chai_001") as ws:
            # Drain initial state message pushed upon connection
            initial_msg = json.loads(ws.receive_text())
            assert initial_msg.get("event") == "TRUST_UPDATED"

            # 2. Reset demo
            resp_reset = test_client.post(
                "/api/simulation/reset",
                json={"vendor_id": "sharma_chai_001"},
            )
            assert resp_reset.status_code == 200

            # Drain reset events from WebSocket
            reset_events = []
            for _ in range(5):
                try:
                    raw = ws.receive_text()
                    data = json.loads(raw)
                    reset_events.append(data)
                    if data.get("event") == "TRUST_UPDATED":
                        break
                except Exception:
                    break

            event_names = [e.get("event") for e in reset_events if "event" in e]
            assert "DEMO_RESET" in event_names
            assert "TRUST_UPDATED" in event_names

            def drain_stage_events():
                events = []
                while True:
                    raw = ws.receive_text()
                    data = json.loads(raw)
                    if "event" in data:
                        events.append(data["event"])
                        if data["event"] == "TRUST_UPDATED":
                            break
                return events

            # 3. Simulate [ +1 Scan ]
            resp_scan = test_client.post(
                "/api/simulation/scan",
                json={"vendor_id": "sharma_chai_001", "amount": 20.0},
            )
            assert resp_scan.status_code == 201

            # Drain events for +1 Scan
            scan_stages = drain_stage_events()
            print("[E2E TEST] Stages received for +1 Scan:", scan_stages)
            assert "SCAN_RECEIVED" in scan_stages
            assert "SCAN_STORED" in scan_stages
            assert "AGGREGATION_UPDATED" in scan_stages
            assert "TRUST_CALCULATED" in scan_stages
            assert "PRIVACY_CHECKED" in scan_stages
            assert "BADGE_UPDATED" in scan_stages
            assert "TRUST_UPDATED" in scan_stages

            # 4. Simulate [ +5 Repeat Customers ]
            resp_burst5 = test_client.post(
                "/api/simulation/burst",
                json={"vendor_id": "sharma_chai_001", "customers": 5},
            )
            assert resp_burst5.status_code == 200
            burst5_data = resp_burst5.json()
            assert burst5_data["repeat_customers_total"] >= 5
            assert burst5_data["tier"] == "GROWING"

            # Drain events from burst 5
            burst5_stages = drain_stage_events()
            print("[E2E TEST] Stages received for +5 Customers:", burst5_stages)
            assert "SCAN_RECEIVED" in burst5_stages
            assert "SCAN_STORED" in burst5_stages
            assert "AGGREGATION_UPDATED" in burst5_stages
            assert "TRUST_CALCULATED" in burst5_stages
            assert "PRIVACY_CHECKED" in burst5_stages
            assert "BADGE_UPDATED" in burst5_stages
            assert "TRUST_UPDATED" in burst5_stages

            # 5. Simulate [ Simulate 45 More Repeat Customers ]
            resp_burst45 = test_client.post(
                "/api/simulation/burst",
                json={"vendor_id": "sharma_chai_001", "customers": 45},
            )
            assert resp_burst45.status_code == 200
            burst45_data = resp_burst45.json()
            assert burst45_data["repeat_customers_total"] >= 50
            assert burst45_data["tier"] == "TRUSTED"
            assert burst45_data["badge_visible"] is True

            # Drain events from burst 45
            burst45_stages = drain_stage_events()
            print("[E2E TEST] Stages received for +45 Customers:", burst45_stages)
            assert "SCAN_RECEIVED" in burst45_stages
            assert "BADGE_UPDATED" in burst45_stages
            assert "TRUST_UPDATED" in burst45_stages

            # 6. Verify GET /api/vendors/sharma_chai_001/stats returns all 8 required dashboard fields
            resp_stats = test_client.get("/api/vendors/sharma_chai_001/stats")
            assert resp_stats.status_code == 200
            stats = resp_stats.json()

            print("[E2E TEST] Vendor Stats for Judge Dashboard:", stats)
            assert stats["trust_tier"] == "TRUSTED"
            assert stats["trust_score"] >= 40.0
            assert stats["repeat_customers"] >= 50
            assert stats["total_scans"] > 100
            assert "consistency_score" in stats
            assert "tenure_days" in stats
            assert "dispute_rate" in stats
            assert "last_updated" in stats
            print("[E2E TEST] All 8 dashboard metrics verified successfully!")
