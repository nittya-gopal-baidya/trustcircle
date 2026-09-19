"""
tests/test_websocket.py
-----------------------
Independent automated verification for the TrustCircle real-time WebSocket system.

Tests:
  1. Connection creation and immediate initial state push (TRUST_UPDATED)
  2. Streaming processing events during scan execution:
     - SCAN_RECEIVED
     - SCAN_STORED
     - AGGREGATION_UPDATED
     - TRUST_CALCULATED
     - PRIVACY_CHECKED
     - BADGE_UPDATED
     - TRUST_UPDATED
  3. Strict privacy verification:
     - customer_hash NEVER transmitted
     - customer identity NEVER transmitted
     - individual scan history NEVER transmitted
  4. Reset event push over WebSocket
"""

import asyncio
import hashlib
import json
import pytest
from starlette.testclient import TestClient

from app.database import close_db, connect_db, scan_events_col, vendor_stats_col, vendors_col
from app.main import app

VENDOR_ID = "sharma_chai_001"


# Note: TestClient handles app lifespan (connect_db/close_db) automatically



def test_websocket_initial_state_on_connect():
    """Verify that connecting to /ws/vendor/{id} immediately delivers the current trust state."""
    with TestClient(app) as client:
        # Reset demo vendor to clean NEW baseline
        client.post("/api/simulation/reset", json={"vendor_id": VENDOR_ID})
        with client.websocket_connect(f"/ws/vendor/{VENDOR_ID}") as ws:
            msg = ws.receive_json()

            assert msg["event"] == "TRUST_UPDATED"
            assert msg["vendor_id"] == VENDOR_ID
            assert "data" in msg

            data = msg["data"]
            assert data["tier"] == "NEW"
            assert data["badge_visible"] is False
            assert "message" in data
            assert "trust_score" in data


def test_websocket_streams_processing_events_and_trust_update():
    """
    Verify that triggering a scan streams all processing events in real time:
      SCAN_RECEIVED -> SCAN_STORED -> AGGREGATION_UPDATED ->
      TRUST_CALCULATED -> PRIVACY_CHECKED -> BADGE_UPDATED -> TRUST_UPDATED
    """
    cust_secret = "secret_customer_identity_98765"
    cust_hash = hashlib.sha256(cust_secret.encode()).hexdigest()

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/vendor/{VENDOR_ID}") as ws:
            # 1. Initial state
            initial = ws.receive_json()
            assert initial["event"] == "TRUST_UPDATED"

            # 2. Trigger a scan via HTTP API
            post_resp = client.post(
                "/api/scans",
                json={
                    "vendor_id": VENDOR_ID,
                    "customer_hash": cust_hash,
                    "amount": 35.0,
                },
            )
            assert post_resp.status_code == 201

            # 3. Read streaming WebSocket events emitted during processing
            received_events = []
            # Expecting at least: SCAN_RECEIVED, SCAN_STORED, AGGREGATION_UPDATED,
            # TRUST_CALCULATED, PRIVACY_CHECKED, BADGE_UPDATED, TRUST_UPDATED
            for _ in range(7):
                payload = ws.receive_json()
                received_events.append(payload)

            event_names = [e.get("event") for e in received_events if "event" in e]

            expected_sequence = [
                "SCAN_RECEIVED",
                "SCAN_STORED",
                "AGGREGATION_UPDATED",
                "TRUST_CALCULATED",
                "PRIVACY_CHECKED",
                "BADGE_UPDATED",
                "TRUST_UPDATED",
            ]

            for expected in expected_sequence:
                assert expected in event_names, f"Expected event '{expected}' in {event_names}"

            # 4. Strict privacy check across ALL received WebSocket messages
            full_ws_text = json.dumps(received_events)
            assert cust_hash not in full_ws_text, "CRITICAL: customer_hash leaked over WebSocket!"
            assert cust_secret not in full_ws_text, "CRITICAL: customer identity leaked over WebSocket!"
            assert "individual_scans" not in full_ws_text

            # 5. Verify format of the main TRUST_UPDATED event
            trust_updated = [e for e in received_events if e.get("event") == "TRUST_UPDATED"][0]
            assert trust_updated["vendor_id"] == VENDOR_ID
            assert "tier" in trust_updated["data"]
            assert "badge_visible" in trust_updated["data"]
            assert "trust_score" in trust_updated["data"]
            assert "message" in trust_updated["data"]


def test_websocket_reset_broadcast():
    """Verify that calling /api/simulation/reset pushes a reset TRUST_UPDATED event."""
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/vendor/{VENDOR_ID}") as ws:
            # Initial connect
            _ = ws.receive_json()

            # Call reset
            res = client.post("/api/simulation/reset", json={"vendor_id": VENDOR_ID})
            assert res.status_code == 200

            # Receive reset broadcasts (DEMO_RESET, TRUST_UPDATED)
            events = []
            for _ in range(2):
                events.append(ws.receive_json())

            event_names = [e.get("event") for e in events]
            assert "DEMO_RESET" in event_names
            assert "TRUST_UPDATED" in event_names

            trust_updated = [e for e in events if e.get("event") == "TRUST_UPDATED"][0]
            assert trust_updated["vendor_id"] == VENDOR_ID
            assert trust_updated["data"]["tier"] == "NEW"
            assert trust_updated["data"]["badge_visible"] is False
