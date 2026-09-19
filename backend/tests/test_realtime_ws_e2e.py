"""
tests/test_realtime_ws_e2e.py
-----------------------------
Pytest verification for the complete real-time WebSocket flow:
NEW (hidden) -> GROWING (visible) -> TRUSTED (visible)
"""

import asyncio
import json
import urllib.request
import pytest
import websockets

HTTP_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/vendor/sharma_chai_001"
VENDOR_ID = "sharma_chai_001"


def post_http(endpoint: str, data: dict):
    url = f"{HTTP_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.mark.anyio
async def test_realtime_tier_transitions_over_websocket():
    """Verify WebSocket transitions: NEW -> GROWING -> TRUSTED in real time."""
    async with websockets.connect(WS_URL) as ws:
        # Initial connect frame
        _ = await ws.recv()

        # Step 1: Reset
        post_http("/api/simulation/reset", {"vendor_id": VENDOR_ID})
        reset_frame = None
        while True:
            frame = await asyncio.wait_for(ws.recv(), timeout=6.0)
            parsed = json.loads(frame)
            if parsed.get("event") == "TRUST_UPDATED":
                reset_frame = parsed
                break
        assert reset_frame["data"]["tier"] == "NEW"
        assert reset_frame["data"]["badge_visible"] is False

        # Step 2: Burst +5 customers -> transitions to GROWING
        post_http("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 5})
        msg2 = None
        while True:
            frame = await asyncio.wait_for(ws.recv(), timeout=6.0)
            parsed = json.loads(frame)
            if parsed.get("event") == "TRUST_UPDATED":
                msg2 = parsed
                break

        assert msg2["data"]["tier"] == "GROWING"
        assert msg2["data"]["badge_visible"] is True

        # Step 3: Burst +45 customers -> transitions to TRUSTED
        post_http("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 45})
        msg3 = None
        while True:
            frame = await asyncio.wait_for(ws.recv(), timeout=6.0)
            parsed = json.loads(frame)
            if parsed.get("event") == "TRUST_UPDATED":
                msg3 = parsed
                break

        assert msg3["data"]["tier"] == "TRUSTED"
        assert msg3["data"]["badge_visible"] is True

        # Step 4: Privacy check
        all_text = json.dumps([reset_frame, msg2, msg3])
        assert "customer_hash" not in all_text
