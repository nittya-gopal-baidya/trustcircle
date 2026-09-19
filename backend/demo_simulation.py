"""
demo_simulation.py
------------------
Interactive verification script for the live TrustCircle Simulation System.
Tests:
  1. Reset
  2. +1 live scan
  3. +5 customers  -> transitions to GROWING
  4. +10 customers -> remains GROWING, builds score
  5. +50 customers -> transitions to TRUSTED
"""

import json
import urllib.request

BASE_URL = "http://localhost:8000"
VENDOR_ID = "sharma_chai_001"


def post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=" * 75)
    print("TRUSTCIRCLE SIMULATION SYSTEM: PROGRESSIVE TIER DEMONSTRATION")
    print("=" * 75)

    # 1. Reset
    print("\n[STEP 1] Resetting vendor 'sharma_chai_001'...")
    res_reset = post("/api/simulation/reset", {"vendor_id": VENDOR_ID})
    print(f"  Result: {res_reset['message']}")

    badge_0 = get(f"/api/vendors/{VENDOR_ID}/badge")
    print(f"  Badge state: tier={badge_0['trust_tier']}, badge_visible={badge_0['badge_visible']}")
    assert badge_0["trust_tier"] == "NEW"
    assert badge_0["badge_visible"] is False

    # 2. Single scan
    print("\n[STEP 2] Simulating +1 live scan event...")
    res_scan = post("/api/simulation/scan", {"vendor_id": VENDOR_ID, "amount": 20.0})
    print(f"  Scan ID: {res_scan['scan_id']}")
    print(f"  Badge visible: {res_scan['badge']['badge_visible']} | Tier: {res_scan['badge']['trust_tier']}")
    print(f"  Pipeline trace executed: {len(res_scan['pipeline_events'])} stages")

    # 3. Burst +5 customers
    print("\n[STEP 3] Simulating burst of +5 repeat customers...")
    res_burst5 = post("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 5})
    print(f"  Repeat customers: {res_burst5['repeat_customers_total']}")
    print(f"  Tier: {res_burst5['tier']}")
    print(f"  Badge visible: {res_burst5['badge_visible']}")
    print(f"  Trust score: {res_burst5['trust_score']}")
    assert res_burst5["repeat_customers_total"] == 5
    assert res_burst5["tier"] == "GROWING"
    assert res_burst5["badge_visible"] is True

    # 4. Burst +10 customers
    print("\n[STEP 4] Simulating burst of +10 repeat customers...")
    res_burst10 = post("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 10})
    print(f"  Repeat customers: {res_burst10['repeat_customers_total']}")
    print(f"  Tier: {res_burst10['tier']}")
    print(f"  Badge visible: {res_burst10['badge_visible']}")
    print(f"  Trust score: {res_burst10['trust_score']}")
    assert res_burst10["repeat_customers_total"] == 15
    assert res_burst10["tier"] == "GROWING"
    assert res_burst10["trust_score"] > res_burst5["trust_score"]

    # 5. Burst +50 customers
    print("\n[STEP 5] Simulating burst of +50 repeat customers...")
    res_burst50 = post("/api/simulation/burst", {"vendor_id": VENDOR_ID, "customers": 50})
    print(f"  Repeat customers: {res_burst50['repeat_customers_total']}")
    print(f"  Tier: {res_burst50['tier']}")
    print(f"  Badge visible: {res_burst50['badge_visible']}")
    print(f"  Trust score: {res_burst50['trust_score']}")
    assert res_burst50["repeat_customers_total"] == 65
    assert res_burst50["tier"] == "TRUSTED"
    assert res_burst50["badge_visible"] is True

    # 6. Fetch customer badge
    print("\n[STEP 6] Customer-facing badge verification (GET /api/vendors/{id}/badge)...")
    final_badge = get(f"/api/vendors/{VENDOR_ID}/badge")
    print(f"  Vendor: {final_badge['vendor_id']}")
    print(f"  Tier: {final_badge['trust_tier']} ({final_badge['tier_label']})")
    print(f"  Badge visible: {final_badge['badge_visible']}")
    print(f"  Approximate scans: {final_badge['total_scans_approx']}")
    print(f"  Tenure days: {final_badge['tenure_days']}")

    # 7. Fetch judge stats
    print("\n[STEP 7] Judge/Demo stats verification (GET /api/vendors/{id}/stats)...")
    final_stats = get(f"/api/vendors/{VENDOR_ID}/stats")
    print(f"  Total scans: {final_stats['total_scans']}")
    print(f"  Unique scanners: {final_stats['unique_scanners']}")
    print(f"  Repeat customers: {final_stats['repeat_customers']}")
    print(f"  Trust score: {final_stats['trust_score']}")
    print(f"  Consistency score: {final_stats.get('consistency_score')}")
    print(f"  Tenure score: {final_stats.get('tenure_score')}")
    print(f"  Dispute score: {final_stats.get('dispute_score')}")

    print("\n" + "=" * 75)
    print("SUCCESS: ALL SIMULATION AND TIER TRANSITION CHECKS PASSED!")
    print("=" * 75)


if __name__ == "__main__":
    main()
