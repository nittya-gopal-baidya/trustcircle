# TrustCircle — Privacy-Preserving Offline Merchant Trust Engine

> **Paytm Hackathon Prototype**: Transforming repeat offline QR scan events into transparent, privacy-preserving merchant trust badges.

---

## 🚀 Quick Start

### 1. Seed Demo Data Across All 4 Tiers

To populate realistic demo data for all four TrustCircle tiers with full signal computation:

```bash
cd backend
python -m app.seed
```

### 2. Start the Backend (FastAPI + WebSocket)

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```
- REST API: `http://localhost:8000`
- WebSocket: `ws://localhost:8000/ws/vendor/{vendor_id}`
- Interactive Docs: `http://localhost:8000/docs`

### 3. Start the Frontend (React + Vite)

```bash
cd frontend
npm run dev -- --port 5173
```
- App URL: `http://localhost:5173`

---

## 🏆 The 4 TrustCircle Tiers

| Tier | Vendor ID | Merchant Name | Category & City | Repeat Customers | Badge Status | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **NEW** | `sharma_chai_001` | Sharma Chai Corner | Tea Stall, Jaipur | **2** (< 5) | **Hidden (k < 5)** | Fresh merchant building history. Badge hidden to prevent deanonymization. |
| **GROWING** | `vendor_growing_cafe` | Ravi's Breakfast & Chai | Quick Service Cafe, Mumbai | **22** (5–49) | **Visible** | Neighborhood cafe with emerging regular patrons. |
| **TRUSTED** | `vendor_trusted_kirana` | Gupta Kirana & General Store | Daily Grocery, Delhi | **130** (50–499) | **Visible** | Established provision store trusted by local families. |
| **COMMUNITY FAVORITE** | `vendor_community_sweets` | Jodhpur Sweets & Namkeen | Confectionery, Jaipur | **560** (500+) | **Visible** | Iconic multi-year heritage business with a large loyal regular community. |

---

## 📊 The 4 Core Signals

Every vendor's trust level is calculated from four statistical signals:

1. **Unique Repeat Customers**: Count of distinct patrons scanning $\ge 3$ times. Determines the tier threshold.
2. **Scan Interval Consistency**: Habitual regularity score computed using the Coefficient of Variation (CV) of visit intervals.
3. **Vendor Tenure**: Days active since merchant creation, benchmarked against 365 days.
4. **Dispute / Chargeback Rate**: Dispute frequency ($\text{dispute\_count} / \text{total\_transactions}$).

---

## 🧪 Running Automated Tests

```bash
cd backend
python -m pytest tests/ -v
```

Includes 26 test suites verifying the trust engine, 7-stage scan pipeline, k-anonymity gate, real-time WebSocket broadcasting, and multi-tier seed validation.
