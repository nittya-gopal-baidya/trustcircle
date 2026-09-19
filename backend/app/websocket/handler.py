"""
websocket/handler.py
--------------------
WebSocket route handler: WS /ws/vendor/{vendor_id}

Connection lifecycle:
  1. Client (e.g. React payment UI) establishes WebSocket connection
  2. Server accepts and registers connection under vendor_id channel
  3. Server immediately pushes current TRUST_UPDATED state
  4. Server streams live pipeline stage events & updated badges on new scans
  5. On disconnect, connection is removed cleanly
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import vendor_stats_col
from app.services.trust_engine import TIER_META, _bucket_scans
from app.websocket.manager import make_badge_message, ws_manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/vendor/{vendor_id}")
async def vendor_badge_ws(vendor_id: str, websocket: WebSocket):
    """
    Live WebSocket feed for vendor trust badges.
    Pushes initial state immediately upon connection, followed by real-time updates.
    """
    await ws_manager.connect(vendor_id, websocket)

    try:
        # ── Step 1: Immediately push current trust state ──────────────────────
        stats = await vendor_stats_col().find_one({"vendor_id": vendor_id}, {"_id": 0})

        if stats:
            tier = stats.get("trust_tier", "NEW")
            badge_visible = stats.get("badge_visible", False)
            trust_score = stats.get("trust_score", 0.0)
            repeat_customers = stats.get("repeat_customers", 0)
            total_scans = stats.get("total_scans", 0)
            tenure_days = stats.get("tenure_days", 0)
        else:
            tier = "NEW"
            badge_visible = False
            trust_score = 0.0
            repeat_customers = 0
            total_scans = 0
            tenure_days = 0

        meta = TIER_META.get(tier, {"label": "New Vendor", "description": None})
        message = make_badge_message(tier, repeat_customers, badge_visible)

        initial_payload = {
            "event": "TRUST_UPDATED",
            "vendor_id": vendor_id,
            "data": {
                "tier": tier,
                "trust_tier": tier,
                "badge_visible": badge_visible,
                "trust_score": round(trust_score, 1),
                "message": message,
                "tier_label": meta["label"],
                "tier_description": meta["description"] if badge_visible else None,
                "total_scans_approx": _bucket_scans(total_scans) if badge_visible else None,
                "tenure_days": tenure_days if badge_visible else None,
                "repeat_customers": repeat_customers if badge_visible else None,
            },
        }

        await ws_manager.send_personal_message(initial_payload, websocket)

        # ── Step 2: Keep connection alive (server-push architecture) ──────────
        while True:
            try:
                data = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Error for vendor='{vendor_id}': {e}")
    finally:
        ws_manager.disconnect(vendor_id, websocket)
