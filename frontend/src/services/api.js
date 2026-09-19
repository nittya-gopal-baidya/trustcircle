/**
 * services/api.js
 * ---------------
 * API service for communicating with the TrustCircle FastAPI backend.
 */

const API_BASE = 'http://localhost:8000';

export async function fetchVendors() {
  const res = await fetch(`${API_BASE}/api/vendors`);
  if (!res.ok) throw new Error(`Failed to load vendors: ${res.statusText}`);
  return res.json();
}

export async function fetchVendor(vendorId) {
  const res = await fetch(`${API_BASE}/api/vendors/${vendorId}`);
  if (!res.ok) throw new Error(`Failed to load vendor: ${res.statusText}`);
  return res.json();
}

export async function fetchVendorBadge(vendorId) {
  const res = await fetch(`${API_BASE}/api/vendors/${vendorId}/badge`);
  if (!res.ok) throw new Error(`Failed to load trust badge: ${res.statusText}`);
  return res.json();
}

export async function fetchVendorStats(vendorId) {
  const res = await fetch(`${API_BASE}/api/vendors/${vendorId}/stats`);
  if (!res.ok) throw new Error(`Failed to load vendor stats: ${res.statusText}`);
  return res.json();
}

export async function submitScan({ vendor_id, customer_hash, amount }) {
  const res = await fetch(`${API_BASE}/api/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vendor_id, customer_hash, amount }),
  });
  if (!res.ok) throw new Error(`Scan failed: ${res.statusText}`);
  return res.json();
}

export async function triggerBurstSimulation({ vendor_id, customers }) {
  const res = await fetch(`${API_BASE}/api/simulation/burst`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vendor_id, customers }),
  });
  if (!res.ok) throw new Error(`Burst failed: ${res.statusText}`);
  return res.json();
}

export async function triggerSingleScanSimulation({ vendor_id, amount }) {
  const res = await fetch(`${API_BASE}/api/simulation/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vendor_id, amount }),
  });
  if (!res.ok) throw new Error(`Scan simulation failed: ${res.statusText}`);
  return res.json();
}

export async function resetSimulation(vendor_id) {
  const res = await fetch(`${API_BASE}/api/simulation/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vendor_id }),
  });
  if (!res.ok) throw new Error(`Reset failed: ${res.statusText}`);
  return res.json();
}
