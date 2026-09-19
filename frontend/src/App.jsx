/**
 * App.jsx
 * -------
 * Main TrustCircle Application.
 *
 * Provides a view switcher between:
 *   1. [ ⚡ Judge Live Processing Dashboard ] - High-telemetry live engine view for hackathon judges
 *   2. [ 📱 Customer Payment Screen ] - Clean mobile checkout screen with dynamic trust badge
 *   3. [ 🔀 Split View ] - Side-by-side view demonstrating simultaneous real-time WebSocket sync
 */

import React, { useState } from 'react';
import TrustDashboard from './components/TrustDashboard';
import PaymentScreen from './components/PaymentScreen';
import './App.css';

export const DEMO_TIER_VENDORS = [
  {
    id: 'sharma_chai_001',
    name: 'Sharma Chai Corner',
    city: 'Jaipur',
    tier: 'NEW',
    regulars: '< 5 regulars',
    badgeText: 'Hidden (k < 5)',
    icon: '☕',
    description: 'Roadside tea stall building initial patron base',
  },
  {
    id: 'vendor_growing_cafe',
    name: "Ravi's Breakfast & Chai",
    city: 'Mumbai',
    tier: 'GROWING',
    regulars: '22 regulars',
    badgeText: '5+ regulars',
    icon: '🥪',
    description: 'Morning snack bar with habitual office crowd',
  },
  {
    id: 'vendor_trusted_kirana',
    name: 'Gupta Kirana Store',
    city: 'Delhi',
    tier: 'TRUSTED',
    regulars: '130 regulars',
    badgeText: '50+ regulars',
    icon: '🏪',
    description: 'Established daily grocery store trusted by families',
  },
  {
    id: 'vendor_community_sweets',
    name: 'Jodhpur Sweets & Namkeen',
    city: 'Jaipur',
    tier: 'COMMUNITY_FAVORITE',
    regulars: '560 regulars',
    badgeText: '500+ regulars',
    icon: '🍬',
    description: 'Historic landmark confectioner with huge loyal following',
  },
];

export default function App() {
  // Default to the Judge Live Dashboard as requested
  const [activeView, setActiveView] = useState('dashboard'); // 'dashboard' | 'payment' | 'split'
  const [selectedVendorId, setSelectedVendorId] = useState('sharma_chai_001');

  return (
    <div className="app-shell">
      {/* ── TOP PRESENTATION NAVIGATION BAR ──────────────────────────────── */}
      <nav className="app-nav-bar" aria-label="Hackathon Mode Navigation">
        <div className="nav-brand">
          <div className="nav-brand-logo">
            <span className="logo-shield">🛡️</span>
            <span className="logo-text">TrustCircle</span>
          </div>
          <span className="nav-badge-pill">Paytm Offline Trust Layer</span>
        </div>

        <div className="nav-tabs-group" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'dashboard'}
            className={`nav-tab-btn ${activeView === 'dashboard' ? 'is-active' : ''}`}
            onClick={() => setActiveView('dashboard')}
            id="tab-judge-dashboard"
          >
            <span className="tab-icon">⚡</span>
            <span className="tab-label">Judge Live Dashboard</span>
            <span className="tab-pulse-tag">Engine</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'payment'}
            className={`nav-tab-btn ${activeView === 'payment' ? 'is-active' : ''}`}
            onClick={() => setActiveView('payment')}
            id="tab-customer-payment"
          >
            <span className="tab-icon">📱</span>
            <span className="tab-label">Customer Payment UI</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'split'}
            className={`nav-tab-btn ${activeView === 'split' ? 'is-active' : ''}`}
            onClick={() => setActiveView('split')}
            id="tab-split-view"
          >
            <span className="tab-icon">🔀</span>
            <span className="tab-label">Split View</span>
            <span className="tab-hint">Dual Screen</span>
          </button>
        </div>
      </nav>

      {/* ── DEMO TIER SHOWCASE SELECTOR ───────────────────────────────────── */}
      <div className="tier-selector-banner" aria-label="Demo Tier Selector">
        <div className="tier-selector-label">
          <span className="tier-selector-title">DEMO TIERS</span>
          <span className="tier-selector-sub">Select seeded vendor to demonstrate:</span>
        </div>
        <div className="tier-selector-pills">
          {DEMO_TIER_VENDORS.map((v, i) => (
            <button
              key={v.id}
              type="button"
              className={`tier-pill-btn tier-pill-btn--${v.tier.toLowerCase()} ${selectedVendorId === v.id ? 'is-selected' : ''}`}
              onClick={() => setSelectedVendorId(v.id)}
              id={`pill-tier-${v.tier.toLowerCase()}`}
            >
              <span className="tier-pill-idx">Tier {i + 1}</span>
              <span className="tier-pill-icon">{v.icon}</span>
              <div className="tier-pill-info">
                <span className="tier-pill-tier">{v.tier.replace('_', ' ')}</span>
                <span className="tier-pill-name">{v.name} ({v.regulars})</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── MAIN CONTENT AREA ────────────────────────────────────────────── */}
      <main className="app-main-content">
        {/* VIEW 1: JUDGE LIVE DASHBOARD */}
        {activeView === 'dashboard' && (
          <div className="view-container view-container--dashboard">
            <TrustDashboard vendorId={selectedVendorId} />
          </div>
        )}

        {/* VIEW 2: CUSTOMER PAYMENT SCREEN */}
        {activeView === 'payment' && (
          <div className="view-container view-container--payment">
            <PaymentScreen vendorId={selectedVendorId} />
          </div>
        )}

        {/* VIEW 3: SPLIT VIEW (DUAL DEMO) */}
        {activeView === 'split' && (
          <div className="view-container view-container--split">
            <div className="split-layout">
              <div className="split-panel split-panel--payment">
                <div className="split-panel-header">
                  <span className="split-panel-tag">CUSTOMER VIEW</span>
                  <h4>Paytm QR Checkout Screen</h4>
                </div>
                <PaymentScreen vendorId={selectedVendorId} />
              </div>

              <div className="split-panel split-panel--dashboard">
                <div className="split-panel-header">
                  <span className="split-panel-tag split-panel-tag--engine">JUDGE VIEW</span>
                  <h4>Real-time Processing Engine</h4>
                </div>
                <TrustDashboard vendorId={selectedVendorId} />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
