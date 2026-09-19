"""
verify_websocket_live.py
------------------------
Independent test script for TrustCircle WebSocket live streaming.
Connects directly to the live running backend at ws://localhost:8000/ws/vendor/sharma_chai_001
"""

import asyncio
import hashlib
import json
import urllib.request
import websockets

WS_URL = "ws://localhost:8000/ws/vendor/sharma_chai_001"
HTTP_URL = "http://localhost:8000"


def send_scan_http(cust_hash: str, amount: float = 30.0):
    url = f"{HTTP_URL}/api/scans"
    req = urllib.request.Request(
        url,
        data=json.dumps({
            "vendor_id": "sharma_chai_001",
            "customer_hash": cust_hash,
            "amount": amount,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


async def test_live_websocket():
    print("=" * 75)
    print("TESTING LIVE WEBSOCKET SYSTEM: ws://localhost:8000/ws/vendor/sharma_chai_001")
    print("=" * 75)

    cust_secret = "vip_customer_999"
    cust_hash = hashlib.sha256(cust_secret.encode()).hexdigest()

    async with websockets.connect(WS_URL) as ws:
        print("\n[1] Connected to WebSocket successfully!")

        # 1. Initial push on connect
        raw_initial = await ws.recv()
        initial = json.loads(raw_initial)
        print(f"    Initial event received: {initial['event']} | tier={initial['data']['tier']}, visible={initial['data']['badge_visible']}")
        assert initial["event"] == "TRUST_UPDATED"
        assert initial["vendor_id"] == "sharma_chai_001"

        # 2. Trigger scan in background
        print("\n[2] Triggering POST /api/scans via HTTP in background...")
        loop = asyncio.get_running_loop()
        scan_future = loop.run_in_executor(None, send_scan_http, cust_hash, 35.0)

        # 3. Read live streaming events
        print("\n[3] Reading live streamed WebSocket events:")
        received_events = []

        # Read the 7 processing events + TRUST_UPDATED
        while len(received_events) < 7:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            parsed = json.loads(msg)
            event_name = parsed.get("event")
            received_events.append(parsed)
            print(f"    <- Received event: [{event_name}] | data={parsed.get('data')}")
            if event_name == "TRUST_UPDATED":
                break

        await scan_future

        # 4. Verify privacy: customer_hash and raw identity NEVER sent over WS
        all_text = json.dumps(received_events)
        assert cust_hash not in all_text, "CRITICAL: customer_hash leaked over WebSocket!"
        assert cust_secret not in all_text, "CRITICAL: customer secret leaked over WebSocket!"
        print("\n[4] PRIVACY VERIFIED: Zero customer hashes or identities transmitted!")

        # 5. Check event presence
        event_names = [e.get("event") for e in received_events]
        print(f"\n[5] Event stream received in sequence: {event_names}")
        assert "TRUST_UPDATED" in event_names
        assert "SCAN_RECEIVED" in event_names
        assert "PRIVACY_CHECKED" in event_names

        print("\n" + "=" * 75)
        print("LIVE WEBSOCKET VERIFICATION PASSED PERFECTLY!")
        print("=" * 75)


if __name__ == "__main__":
    asyncio.run(test_live_websocket())
