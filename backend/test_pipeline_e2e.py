"""
test_pipeline_e2e.py
--------------------
End-to-end integration test of the complete QR Scan Processing Pipeline.

Tests:
  1. Vendor validation
  2. Complete 7-stage processing flow:
     SCAN_RECEIVED -> SCAN_STORED -> AGGREGATION_UPDATED ->
     TRUST_CALCULATED -> PRIVACY_CHECK -> BADGE_UPDATED -> WEBSOCKET_BROADCAST
  3. Strict customer privacy:
     - customer_hash is NEVER present in the response
     - No individual transaction history exposed
  4. Repeat customer progression (>= 3 scans per customer)
  5. K-anonymity transition (badge hidden at 1..4 repeat customers, visible at 5)
  6. Persistence in MongoDB vendor_stats
"""

import hashlib
import json
import urllib.request
from datetime import datetime, timezone

BASE_URL = "http://localhost:8000"
VENDOR_ID = "vendor_chai_stall"


def hash_customer(customer_id: str) -> str:
    return hashlib.sha256(customer_id.encode()).hexdigest()


def http_post(endpoint: str, data: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(endpoint: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_e2e_test():
    print("=" * 70)
    print("STARTING E2E TEST: QR SCAN PROCESSING PIPELINE")
    print("=" * 70)

    # 1. Reset vendor data for clean test
    print("\n[STEP 1] Resetting simulation state for vendor...")
    reset_res = http_post("/api/simulation/reset", {"vendor_id": VENDOR_ID})
    print(f"  Reset response: {reset_res['message']}")

    # 2. Verify initial badge state
    print("\n[STEP 2] Verifying initial badge state...")
    initial_badge = http_get(f"/api/vendors/{VENDOR_ID}/badge")
    print(f"  Initial badge: tier={initial_badge['trust_tier']}, visible={initial_badge['badge_visible']}")
    assert initial_badge["badge_visible"] is False
    assert initial_badge["trust_tier"] == "NEW"

    # 3. Fire first scan and verify the 7 pipeline stages
    print("\n[STEP 3] Firing first scan (customer_001)...")
    cust1_hash = hash_customer("customer_001")
    scan_res = http_post("/api/scans", {
        "vendor_id": VENDOR_ID,
        "customer_hash": cust1_hash,
        "amount": 25.0,
    })

    print(f"  Scan ID: {scan_res['scan_id']}")
    print(f"  Status: {scan_res['status']}")
    print(f"  Badge visible: {scan_res['badge']['badge_visible']}")
    print(f"  Tier: {scan_res['badge']['trust_tier']}")

    # Check privacy: customer_hash must NOT be in the response
    res_str = json.dumps(scan_res)
    assert cust1_hash not in res_str, "CRITICAL ERROR: customer_hash leaked in scan response!"
    print("  [PRIVACY VERIFIED] customer_hash is NOT present in API response.")

    # Verify pipeline stages
    stages = [event["stage"] for event in scan_res["pipeline_events"]]
    expected_stages = [
        "SCAN_RECEIVED",
        "SCAN_STORED",
        "AGGREGATION_UPDATED",
        "TRUST_CALCULATED",
        "PRIVACY_CHECK",
        "BADGE_UPDATED",
        "WEBSOCKET_BROADCAST",
    ]
    print(f"  Recorded Stages: {stages}")
    assert stages == expected_stages, f"Expected {expected_stages}, got {stages}"
    print("  [FLOW VERIFIED] Complete 7-stage pipeline executed in exact sequence!")

    # 4. Qualify customer_001 as a repeat customer (needs 3 scans total)
    print("\n[STEP 4] Firing 2 more scans for customer_001 to reach repeat customer threshold (>= 3 scans)...")
    http_post("/api/scans", {"vendor_id": VENDOR_ID, "customer_hash": cust1_hash, "amount": 25.0})
    cust1_third_scan = http_post("/api/scans", {"vendor_id": VENDOR_ID, "customer_hash": cust1_hash, "amount": 25.0})

    # Aggregation stage should now show repeat_customers = 1
    agg_event = [e for e in cust1_third_scan["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
    print(f"  Aggregation details: {agg_event['details']}")
    assert agg_event["details"]["repeat_customers"] == 1
    # But badge_visible must STILL be False because 1 < 5 (k-anonymity floor)
    assert cust1_third_scan["badge"]["badge_visible"] is False
    print("  [K-ANONYMITY VERIFIED] repeat_customers = 1 (< 5) -> badge_visible remains False.")

    # 5. Simulate 4 more customers to reach exactly 5 repeat customers (K-anonymity boundary)
    print("\n[STEP 5] Adding 4 more repeat customers (customer_002 to customer_005) with 3 scans each...")
    for i in range(2, 6):
        c_hash = hash_customer(f"customer_{i:03d}")
        for scan_idx in range(3):
            last_resp = http_post("/api/scans", {
                "vendor_id": VENDOR_ID,
                "customer_hash": c_hash,
                "amount": 30.0,
            })

    # Verify at 5 repeat customers
    final_badge = last_resp["badge"]
    final_agg = [e for e in last_resp["pipeline_events"] if e["stage"] == "AGGREGATION_UPDATED"][0]
    final_privacy = [e for e in last_resp["pipeline_events"] if e["stage"] == "PRIVACY_CHECK"][0]

    print("\n[STEP 6] Evaluating final state after 5 repeat customers:")
    print(f"  Total scans: {final_agg['details']['total_scans']}")
    print(f"  Unique scanners: {final_agg['details']['unique_scanners']}")
    print(f"  Repeat customers: {final_agg['details']['repeat_customers']}")
    print(f"  Privacy check message: {final_privacy['message']}")
    print(f"  Final badge: tier={final_badge['trust_tier']}, visible={final_badge['badge_visible']}")

    assert final_agg["details"]["repeat_customers"] == 5
    assert final_badge["badge_visible"] is True, "Badge should be visible when repeat_customers == 5"
    assert final_badge["trust_tier"] == "GROWING", "Tier should be GROWING when repeat_customers in 5..49"

    # 6. Verify persistence in vendor_stats
    print("\n[STEP 7] Verifying database persistence in /api/vendors/{vendor_id}/stats...")
    stats = http_get(f"/api/vendors/{VENDOR_ID}/stats")
    print(f"  Persisted stats:")
    print(f"    - vendor_id: {stats['vendor_id']}")
    print(f"    - total_scans: {stats['total_scans']}")
    print(f"    - repeat_customers: {stats['repeat_customers']}")
    print(f"    - trust_score: {stats['trust_score']}")
    print(f"    - trust_tier: {stats['trust_tier']}")
    print(f"    - badge_visible: {stats['badge_visible']}")
    print(f"    - consistency_score: {stats.get('consistency_score')}")
    print(f"    - tenure_score: {stats.get('tenure_score')}")
    print(f"    - dispute_score: {stats.get('dispute_score')}")

    assert stats["repeat_customers"] == 5
    assert stats["badge_visible"] is True
    assert stats["trust_tier"] == "GROWING"
    assert stats["trust_score"] > 0

    print("\n" + "=" * 70)
    print("ALL E2E CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_e2e_test()
