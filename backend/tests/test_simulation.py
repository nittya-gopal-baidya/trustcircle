"""
tests/test_simulation.py
-------------------------
Integration tests for the TrustCircle Simulation Engine.

Verifies:
  1. POST /api/simulation/reset cleans vendor state (NEW tier, badge hidden)
  2. POST /api/simulation/scan triggers individual live processing (1 scan)
  3. POST /api/simulation/burst generates realistic repeat scans (3–5 per customer)
  4. Progressive trust tier transitions:
     NEW (0–4 repeat customers)
       ↓ (+5 customers)
     GROWING (5–49 repeat customers)
       ↓ (+10 customers)
     GROWING (15 repeat customers)
       ↓ (+50 customers)
     TRUSTED (65 repeat customers >= 50)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import close_db, connect_db
from app.main import app

VENDOR_ID = "sharma_chai_001"


@pytest.fixture(autouse=True)
async def db_lifecycle():
    await connect_db()
    yield
    await close_db()


@pytest.mark.anyio
async def test_full_simulation_progression_flow():
    """
    Test the complete demo journey requested:
      - Reset to clean initial state (NEW tier, badge hidden)
      - +1 scan (individual live processing, still NEW)
      - +5 customers (transitions to GROWING, unlocks badge at K=5)
      - +10 customers (remains GROWING, increases trust score)
      - +50 customers (transitions to TRUSTED)
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ── 1. TEST RESET ─────────────────────────────────────────────────────
        reset_res = await client.post("/api/simulation/reset", json={"vendor_id": VENDOR_ID})
        assert reset_res.status_code == 200
        assert reset_res.json()["status"] == "ok"

        # Verify badge after reset
        badge_res = await client.get(f"/api/vendors/{VENDOR_ID}/badge")
        assert badge_res.status_code == 200
        badge_data = badge_res.json()
        assert badge_data["trust_tier"] == "NEW"
        assert badge_data["badge_visible"] is False
        print("\n[VERIFIED] Reset successful: tier=NEW, badge_visible=False")

        # ── 2. TEST +1 SCAN ───────────────────────────────────────────────────
        single_scan_res = await client.post(
            "/api/simulation/scan",
            json={"vendor_id": VENDOR_ID, "amount": 25.0},
        )
        assert single_scan_res.status_code == 201
        scan_data = single_scan_res.json()
        assert scan_data["status"] == "success"
        assert scan_data["badge"]["badge_visible"] is False
        assert scan_data["badge"]["trust_tier"] == "NEW"
        # Verify all 7 pipeline stages were logged
        stages = [e["stage"] for e in scan_data["pipeline_events"]]
        assert len(stages) == 7
        print("[VERIFIED] +1 single scan: executed 7 pipeline stages, still NEW (0 repeat customers)")

        # ── 3. TEST +5 CUSTOMERS (TRANSITION TO GROWING) ──────────────────────
        burst_5_res = await client.post(
            "/api/simulation/burst",
            json={"vendor_id": VENDOR_ID, "customers": 5},
        )
        assert burst_5_res.status_code == 200
        burst_5 = burst_5_res.json()
        assert burst_5["status"] == "ok"
        assert burst_5["customers_simulated"] == 5
        assert burst_5["scans_inserted"] >= 15  # At least 3 scans per customer
        assert burst_5["repeat_customers_total"] == 5

        # Key verification: K-anonymity boundary reached (5 repeat customers)
        assert burst_5["badge_visible"] is True, "Badge must unlock when repeat_customers == 5"
        assert burst_5["tier"] == "GROWING", "Tier must transition to GROWING at 5 repeat customers"
        print(f"[VERIFIED] +5 customers: repeat={burst_5['repeat_customers_total']}, tier={burst_5['tier']}, badge_visible=True")

        # ── 4. TEST +10 CUSTOMERS (EXPANDING GROWING TIER) ────────────────────
        burst_10_res = await client.post(
            "/api/simulation/burst",
            json={"vendor_id": VENDOR_ID, "customers": 10},
        )
        assert burst_10_res.status_code == 200
        burst_10 = burst_10_res.json()
        assert burst_10["repeat_customers_total"] == 15
        assert burst_10["tier"] == "GROWING", "15 repeat customers is still GROWING (5–49)"
        assert burst_10["badge_visible"] is True
        assert burst_10["trust_score"] > burst_5["trust_score"], "Trust score should rise with more repeat customers"
        print(f"[VERIFIED] +10 customers: repeat={burst_10['repeat_customers_total']}, tier={burst_10['tier']}, score={burst_10['trust_score']}")

        # ── 5. TEST +50 CUSTOMERS (TRANSITION TO TRUSTED) ─────────────────────
        burst_50_res = await client.post(
            "/api/simulation/burst",
            json={"vendor_id": VENDOR_ID, "customers": 50},
        )
        assert burst_50_res.status_code == 200
        burst_50 = burst_50_res.json()
        # Total repeat customers is now 15 + 50 = 65
        assert burst_50["repeat_customers_total"] == 65
        assert burst_50["tier"] == "TRUSTED", "65 repeat customers qualifies for TRUSTED tier (50–499)"
        assert burst_50["badge_visible"] is True
        print(f"[VERIFIED] +50 customers: repeat={burst_50['repeat_customers_total']}, tier={burst_50['tier']}, score={burst_50['trust_score']}")

        # ── 6. VERIFY PERSISTENCE IN VENDOR STATS ─────────────────────────────
        stats_res = await client.get(f"/api/vendors/{VENDOR_ID}/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["vendor_id"] == VENDOR_ID
        assert stats["repeat_customers"] == 65
        assert stats["trust_tier"] == "TRUSTED"
        assert stats["badge_visible"] is True
        print("[VERIFIED] All persistence and tier transitions confirmed!")
