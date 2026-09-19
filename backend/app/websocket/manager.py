"""
websocket/manager.py
--------------------
Thread-safe (asyncio) WebSocket connection manager for TrustCircle.

Features:
  - Manages active client connections keyed by vendor_id
  - Broadcasts structured lifecycle events:
      * SCAN_RECEIVED
      * SCAN_STORED
      * AGGREGATION_UPDATED
      * TRUST_CALCULATED
      * PRIVACY_CHECKED
      * BADGE_UPDATED
      * TRUST_UPDATED (main badge payload)
  - Strict privacy enforcement: NEVER includes customer_hash or individual history
"""

import json
from collections import defaultdict
from typing import Any, Optional
from fastapi import WebSocket


def make_badge_message(tier: str, repeat_customers: int, badge_visible: bool) -> str:
    """Generate concise, human-friendly trust badge message for customers."""
    if not badge_visible or repeat_customers < 5:
        return "Building history..."
    elif tier == "GROWING":
        return "5+ regulars trust this vendor"
    elif tier == "TRUSTED":
        return "50+ regulars trust this vendor"
    else:  # COMMUNITY_FAVORITE
        return "500+ regulars trust this community favorite"


class ConnectionManager:
    """
    Manages active WebSocket connections per vendor.
    Allows point-to-point sends and vendor channel broadcasts.
    """

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, vendor_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket client for a vendor."""
        await websocket.accept()
        self.active_connections[vendor_id].append(websocket)
        print(f"[WS] Client connected: vendor='{vendor_id}' | total_active={len(self.active_connections[vendor_id])}")

    def disconnect(self, vendor_id: str, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        connections = self.active_connections.get(vendor_id, [])
        if websocket in connections:
            connections.remove(websocket)
        print(f"[WS] Client disconnected: vendor='{vendor_id}' | remaining={len(connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """Send a JSON payload directly to a single WebSocket client."""
        await websocket.send_text(json.dumps(message))

    async def broadcast(self, vendor_id: str, payload: dict) -> None:
        """
        Broadcast a raw JSON payload to all active clients watching vendor_id.
        Dead or disconnected clients are silently purged.
        """
        connections = self.active_connections.get(vendor_id, [])
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(vendor_id, ws)

    async def broadcast_event(self, vendor_id: str, event_name: str, data: dict[str, Any]) -> None:
        """
        Broadcast a standardized event envelope to all clients watching vendor_id.
        Payload structure:
        {
            "event": event_name,
            "vendor_id": vendor_id,
            "data": data
        }
        """
        payload = {
            "event": event_name,
            "vendor_id": vendor_id,
            "data": data,
        }
        await self.broadcast(vendor_id, payload)

    async def broadcast_trust_update(
        self,
        vendor_id: str,
        tier: str,
        badge_visible: bool,
        trust_score: float,
        repeat_customers: int,
        message: Optional[str] = None,
        tier_label: Optional[str] = None,
        tier_description: Optional[str] = None,
        total_scans_approx: Optional[str] = None,
        tenure_days: Optional[int] = None,
        total_scans: Optional[int] = None,
        consistency_score: Optional[float] = None,
        dispute_rate: Optional[float] = None,
        last_updated: Optional[str] = None,
    ) -> None:
        """
        Broadcast the primary TRUST_UPDATED event format with complete metrics
        for both the customer payment badge and the judge live engine dashboard.
        """
        msg = message or make_badge_message(tier, repeat_customers, badge_visible)
        data = {
            "tier": tier,
            "trust_tier": tier,  # Alias for backward compatibility
            "badge_visible": badge_visible,
            "trust_score": round(trust_score, 1),
            "message": msg,
            "tier_label": tier_label or ("New Vendor" if tier == "NEW" else tier.title()),
            "tier_description": tier_description if badge_visible else None,
            "total_scans_approx": total_scans_approx if badge_visible else None,
            "tenure_days": tenure_days if tenure_days is not None else 0,
            "repeat_customers": repeat_customers,
            "total_scans": total_scans if total_scans is not None else 0,
            "scan_consistency": consistency_score if consistency_score is not None else 0.0,
            "consistency_score": consistency_score if consistency_score is not None else 0.0,
            "dispute_rate": dispute_rate if dispute_rate is not None else 0.0,
            "last_updated": last_updated or datetime.now(timezone.utc).isoformat(),
        }
        await self.broadcast_event(vendor_id, "TRUST_UPDATED", data)

    def connection_count(self, vendor_id: str) -> int:
        """Return the number of active clients watching a vendor."""
        return len(self.active_connections.get(vendor_id, []))


# Singleton instance shared across FastAPI application
ws_manager = ConnectionManager()
