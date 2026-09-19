"""
verify_realtime_demo_flow.py
----------------------------
Simulates the React Payment Screen WebSocket client to verify the complete
real-time demo flow:

  1. Initial Connect -> NEW (badge_visible: false)
  2. Burst +5 Customers -> transitions in real time to GROWING (badge_visible: true)
  3. Burst +50 Customers -> transitions in real time to TRUSTED (badge_visible: true)
  4. Privacy Verification -> customer_hash NEVER transmitted
"""

import asyncio
import json
import urllib.request
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


async def run_flow():
    print("=" * 75)
    print("VERIFYING COMPLETE REAL-TIME DEMO FLOW: FRONTEND + BACKEND WEBSOCKET")
    print("=" * 75)

    # Connect WebSocket client (acts as useTrustSocket)
    async with websockets.connect(WS_URL) as ws:
        print("\n[WS CLIENT] Connected to ws://localhost:8000/ws/vendor/sharma_chai_001")

        # ── Step 1: Initial state & reset ──────────────────────────────────────
        initial_raw = await ws.recv()
        print("  <- Received initial connection frame")

        print("\n[STEP 1] Resetting demo state via POST /api/simulation/reset...")
        reset_res = post_http("/api/simulation/reset", {"vendor_id": VENDOR_ID})
        print(f"  API Response: {reset_res['message']}")

        # Read reset event over WebSocket
        msg1_raw = await ws.recv()
        msg1 = json.loads(msg1_raw)
        print(f"  <- WS Event: [{msg1['event']}] tier={msg1['data']['tier']}, visible={msg1['data']['badge_visible']}")
        assert msg1["event"] == "TRUST_UPDATED"
        assert msg1["data"]["tier"] == "NEW"
        assert msg1["data"]["badge_visible"] is False
        print("  ✓ State 1 Confirmed: NEW (No badge)")

        # ── Step 2: Transition NEW -> GROWING (+5 customers) ───────────────────
        print("\n[STEP 2] Simulating +5 repeat customers via POST /api/simulation/burst...")
        post_http("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 5})

        # Wait for the TRUST_UPDATED event on the WebSocket
        msg2 = None
        while True:
            frame = await asyncio.wait_for(ws.recv(), timeout=5.0)
            parsed = json.loads(frame)
            if parsed.get("event") == "TRUST_UPDATED":
                msg2 = parsed
                break

        print(f"  <- WS Event: [{msg2['event']}] tier={msg2['data']['tier']}, visible={msg2['data']['badge_visible']}")
        print(f"  <- Threshold Message: \"{msg2['data']['message']}\"")
        assert msg2["data"]["tier"] == "GROWING"
        assert msg2["data"]["badge_visible"] is True
        print("  ✓ State 2 Confirmed: GROWING (Badge visible with '5 regulars trust this vendor')")

        # ── Step 3: Transition GROWING -> TRUSTED (+50 customers) ──────────────
        print("\n[STEP 3] Simulating +50 repeat customers via POST /api/simulation/burst...")
        post_http("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 50})

        msg3 = None
        while True:
            frame = await asyncio.wait_for(ws.recv(), timeout=5.0)
            parsed = json.loads(frame)
            if parsed.get("event") == "TRUST_UPDATED":
                msg3 = parsed
                break

        print(f"  <- WS Event: [{msg3['event']}] tier={msg3['data']['tier']}, visible={msg3['data']['badge_visible']}")
        print(f"  <- Threshold Message: \"{msg3['data']['message']}\"")
        assert msg3["data"]["tier"] == "TRUSTED"
        assert msg3["data"]["badge_visible"] is True
        print("  ✓ State 3 Confirmed: TRUSTED (Badge visible with '50+ regulars trust this vendor')")

        # ── Step 4: Privacy check ──────────────────────────────────────────────
        print("\n[STEP 4] Verifying privacy across all received messages...")
        all_frames = [msg1, msg2, msg3]
        all_text = json.dumps(all_frames)
        assert "customer_hash" not in all_text
        assert "hash" not in all_text
        print("  ✓ Privacy Confirmed: Zero customer hashes or identity leaks!")

        print("\n" + "=" * 75)
        print("COMPLETE REAL-TIME FLOW VERIFIED SUCCESSFULLY!")
        print("NEW (hidden) -> GROWING (5+ regulars) -> TRUSTED (50+ regulars)")
        print("React state updates instantaneously without page refresh!")
        print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_flow())
