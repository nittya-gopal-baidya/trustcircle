# TrustCircle — Hackathon MVP Architecture Plan

A trust-signal system for offline vendors, surfaced at QR scan/payment time.
The system aggregates repeat-scan behavior to compute a vendor trust tier and displays it to customers in real time.

---

## 1. Project Architecture

```
Simulator (Python script)
        │  POST /api/scans   (simulated QR scan event)
        ▼
FastAPI Backend
        │  • Stores raw scan in MongoDB
        │  • Triggers async trust recalculation
        ▼
MongoDB
        │  • scans collection (raw events)
        │  • vendor_trust collection (aggregated trust state)
        ▼
Trust Engine (Python module)
        │  • Aggregates unique repeat customers
        │  • Applies k-anonymity floor (k=5)
        │  • Assigns tier: NEW / GROWING / TRUSTED / COMMUNITY_FAVORITE
        ▼
Badge API  GET /api/badge/{vendor_id}
        │  • Returns tier + privacy-safe summary
        ▼
WebSocket  ws://…/ws/vendor/{vendor_id}
        │  • Pushes badge updates to all connected clients
        ▼
React Payment UI
        │  • Customer scans QR → opens payment page
        │  • Badge appears if k-anonymity floor is met
        │  • Live updates via WebSocket
```

---

## 2. Folder Structure

```
trustcircle/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py            # Env vars, MongoDB URI, constants
│   │   ├── database.py          # Motor (async MongoDB) client
│   │   │
│   │   ├── models/
│   │   │   ├── scan.py          # Pydantic model: ScanEvent
│   │   │   └── trust.py         # Pydantic model: VendorTrust, BadgeResponse
│   │   │
│   │   ├── routers/
│   │   │   ├── scans.py         # POST /api/scans
│   │   │   ├── badge.py         # GET  /api/badge/{vendor_id}
│   │   │   └── websocket.py     # WS   /ws/vendor/{vendor_id}
│   │   │
│   │   ├── services/
│   │   │   ├── trust_engine.py  # Core trust calculation logic
│   │   │   └── ws_manager.py    # WebSocket connection manager
│   │   │
│   │   └── simulator/
│   │       └── simulate_scans.py  # Standalone script to fire fake scan events
│   │
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   │
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       │
│       ├── components/
│       │   ├── TrustBadge.jsx       # Badge UI (tier + icon + label)
│       │   ├── BadgeHidden.jsx      # Shown when k-anonymity not met
│       │   ├── VendorCard.jsx       # Vendor info wrapper
│       │   └── ScanSimulator.jsx    # UI button to trigger simulated scans
│       │
│       ├── hooks/
│       │   └── useTrustSocket.js    # Custom hook: WebSocket + badge state
│       │
│       ├── pages/
│       │   └── PaymentPage.jsx      # Main customer-facing page
│       │
│       └── assets/
│           └── tier-icons/          # SVG icons per trust tier
```

---

## 3. MongoDB Collections

### Collection: `scans`
Raw QR scan/payment events. One document per scan.

```json
{
  "_id": ObjectId,
  "vendor_id": "vendor_abc",          // vendor identifier (QR code owner)
  "customer_hash": "sha256(...)",      // hashed customer identifier (never exposed via API)
  "timestamp": ISODate,
  "amount_simulated": 150.00,          // simulated payment amount (INR)
  "session_id": "uuid"                 // dedup guard per scan session
}
```

**Indexes:**
- `{ vendor_id: 1, customer_hash: 1 }` — for repeat-customer aggregation
- `{ vendor_id: 1, timestamp: -1 }` — for interval consistency calculation
- `{ session_id: 1 }` — unique, for idempotency

---

### Collection: `vendor_trust`
Aggregated trust state per vendor. Upserted after every scan.

```json
{
  "_id": ObjectId,
  "vendor_id": "vendor_abc",
  "tier": "GROWING",                   // NEW | GROWING | TRUSTED | COMMUNITY_FAVORITE
  "unique_repeat_customers": 12,        // internal count (not exposed if < 5)
  "total_scans": 87,
  "avg_scan_interval_hours": 4.2,       // consistency signal
  "tenure_days": 45,                    // days since first scan
  "dispute_rate": 0.01,                 // simulated dispute/chargeback ratio
  "k_anonymous": true,                  // true if unique_repeat_customers >= 5
  "last_updated": ISODate
}
```

**Indexes:**
- `{ vendor_id: 1 }` — unique

---

### Collection: `vendors` *(optional — for demo seed data)*
Static vendor metadata for display in the UI.

```json
{
  "_id": ObjectId,
  "vendor_id": "vendor_abc",
  "name": "Ravi's Chai Stall",
  "category": "Food & Beverage",
  "city": "Mumbai",
  "registered_since": ISODate
}
```

---

## 4. API Endpoints

### POST `/api/scans` — Ingest a simulated scan event
**Request body:**
```json
{
  "vendor_id": "vendor_abc",
  "customer_hash": "sha256_of_customer_id",
  "amount_simulated": 150.00
}
```
**Response:**
```json
{ "scan_id": "uuid", "status": "recorded" }
```
**Side effects:**
- Saves scan to `scans` collection
- Calls Trust Engine → upserts `vendor_trust`
- Broadcasts updated badge via WebSocket to all clients watching `vendor_id`

---

### GET `/api/badge/{vendor_id}` — Customer-facing badge (privacy-safe)
**Response (k-anonymous, tier visible):**
```json
{
  "vendor_id": "vendor_abc",
  "show_badge": true,
  "tier": "GROWING",
  "label": "Growing Trust",
  "tier_description": "Trusted by a growing number of repeat customers",
  "total_scans_approx": "80+",   // bucketed, never exact
  "tenure_days": 45
}
```
**Response (below k-anonymity floor):**
```json
{
  "vendor_id": "vendor_abc",
  "show_badge": false,
  "tier": "NEW",
  "label": null,
  "tier_description": null
}
```
> Raw `unique_repeat_customers` count and `customer_hash` are **never** returned.

---

### GET `/api/vendors` — List all vendors (for demo dropdown)
Returns seed vendor names + IDs.

---

### GET `/api/vendor/{vendor_id}/stats` — Internal debug stats *(judge/demo only)*
Returns full trust document including raw count. Clearly labeled as internal.

---

### WebSocket `/ws/vendor/{vendor_id}` — Live badge push
- Client connects when payment page opens.
- Server pushes `BadgeUpdate` JSON whenever trust state changes.
- Message shape mirrors GET `/api/badge/{vendor_id}` response.

---

## 5. WebSocket Flow

```
Customer opens PaymentPage for vendor_abc
        │
        ▼
React useTrustSocket hook
  → connects to ws://localhost:8000/ws/vendor/vendor_abc
  → stores in ConnectionManager (server side)

Another customer scans QR (or simulator fires)
        │
        ▼
POST /api/scans
  → Trust Engine recalculates vendor_abc trust
  → vendor_trust document upserted
  → ws_manager.broadcast("vendor_abc", badge_payload)
        │
        ▼
All WebSocket clients watching vendor_abc
  → receive JSON push
  → React state updates → badge re-renders
```

**Server-side `ws_manager.py` design:**
```python
class ConnectionManager:
    # Dict[vendor_id -> List[WebSocket]]
    active_connections: dict[str, list[WebSocket]]

    async def connect(vendor_id, websocket)
    def disconnect(vendor_id, websocket)
    async def broadcast(vendor_id, message: dict)
```

---

## 6. Trust Engine Design

**File:** `app/services/trust_engine.py`

### Step 1 — Aggregate repeat customers
```
For a given vendor_id:
  Query scans collection, group by customer_hash
  Count customers where scan_count >= 3
  → unique_repeat_customers
```

### Step 2 — Compute interval consistency
```
For each customer_hash with >= 2 scans:
  Sort scans by timestamp
  Compute gaps between consecutive scans
Average all gaps → avg_scan_interval_hours
Low variance = high consistency (future signal weight)
```

### Step 3 — Compute tenure
```
tenure_days = (now - first_scan_timestamp_for_vendor).days
```

### Step 4 — Dispute rate (simulated)
```
dispute_rate = disputes / total_scans
(Injected randomly by simulator at low base rate ~1%)
```

### Step 5 — Apply k-anonymity floor
```python
K_FLOOR = 5

if unique_repeat_customers < K_FLOOR:
    tier = "NEW"
    k_anonymous = False
    # badge is hidden — never expose count via customer API
else:
    k_anonymous = True
    # proceed to tier assignment
```

### Step 6 — Assign trust tier
```python
def assign_tier(unique_repeat_customers: int) -> str:
    if unique_repeat_customers < 5:
        return "NEW"
    elif unique_repeat_customers < 50:
        return "GROWING"
    elif unique_repeat_customers < 500:
        return "TRUSTED"
    else:
        return "COMMUNITY_FAVORITE"
```

### Step 7 — Upsert `vendor_trust`
Atomic upsert with the full computed state. Then broadcast via WebSocket.

---

## Open Questions

> [!IMPORTANT]
> **Simulator behavior**: Should the simulator generate scans in real-time (streaming, e.g. one every few seconds) for a live demo effect, or should it support a "bulk load" mode to pre-populate data quickly for judges?
> Recommendation: support both — a `--mode realtime|bulk` flag.

> [!IMPORTANT]
> **Vendor seeding**: Should we pre-seed a handful of demo vendors at different trust tiers (e.g., one NEW, one GROWING, one TRUSTED, one COMMUNITY_FAVORITE) so judges can see all four badge states immediately?

> [!NOTE]
> **Dispute rate**: Since we can't simulate actual disputes meaningfully, should we let the simulator randomly inject ~1% dispute events, or expose a manual "inject dispute" button in the UI for a live demo?

> [!NOTE]
> **Customer identity**: The simulator will hash a rotating pool of fake `customer_id` values (e.g., `cust_001`…`cust_999`) using SHA-256 before storing. This preserves the privacy architecture even in simulation.

---

## Verification Plan

### After each build step
- Run backend with `uvicorn main:app --reload`
- Hit endpoints via Swagger UI at `/docs`
- Run simulator script and watch WebSocket push in browser dev tools
- Verify badge is hidden for `unique_repeat_customers < 5`
- Verify badge appears at correct tier thresholds

### Manual demo flow
1. Open React UI on `vendor_abc` payment page
2. Run simulator in `bulk` mode to cross tier thresholds
3. Watch badge animate through NEW → GROWING → TRUSTED → COMMUNITY_FAVORITE live
