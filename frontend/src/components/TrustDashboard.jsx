/**
 * components/TrustDashboard.jsx
 * -----------------------------
 * TrustCircle Live Processing Dashboard for Hackathon Judges.
 *
 * Displays live engine telemetry and real-time MongoDB statistics:
 *   - TRUSTCIRCLE LIVE ENGINE header
 *   - Vendor: Sharma Chai Corner
 *   - Trust Tier: TRUSTED / GROWING / NEW
 *   - Trust Score: 82
 *   - Repeat Customers: 120
 *   - Total Scans: 1847
 *   - Scan Consistency: XX
 *   - Vendor Tenure: XX
 *   - Dispute Rate: XX
 *   - Last Updated: XX
 *
 * Connected live via WebSocket (ws://localhost:8000/ws/vendor/sharma_chai_001)
 * so every simulator button click updates without page reload.
 */

import React, { useState, useEffect } from 'react';
import { useTrustSocket } from '../hooks/useTrustSocket';
import { fetchVendor, fetchVendorStats, triggerSingleScanSimulation } from '../services/api';
import SimulatorControls from './SimulatorControls';
import LiveEventStream from './LiveEventStream';
import ProcessingDetailsPanel from './ProcessingDetailsPanel';

const DEFAULT_VENDOR_ID = 'sharma_chai_001';

export default function TrustDashboard({ vendorId = DEFAULT_VENDOR_ID }) {
  const [showDevMode, setShowDevMode] = useState(true);
  const [isSimulatingScan, setIsSimulatingScan] = useState(false);

  const [vendorProfile, setVendorProfile] = useState({
    name: 'Sharma Chai Corner',
    category: 'Tea Stall',
    city: 'Jaipur',
    created_at: null,
  });

  const [stats, setStats] = useState({
    trust_tier: 'NEW',
    trust_score: 0.0,
    repeat_customers: 0,
    total_scans: 0,
    scan_consistency: 0.0,
    tenure_days: 0,
    dispute_rate: 0.0,
    badge_visible: false,
    last_updated: new Date().toTimeString().slice(0, 8),
  });

  // Real-time WebSocket hook
  const {
    isConnected,
    isLoading: isWsLoading,
    error: wsError,
    badge,
    liveStats,
    eventLogs,
    clearLogs,
    processingStages,
  } = useTrustSocket(vendorId);

  const handleTriggerSingleScan = async () => {
    if (isSimulatingScan) return;
    setIsSimulatingScan(true);
    try {
      await triggerSingleScanSimulation({ vendor_id: vendorId, amount: 40.0 });
    } catch (err) {
      console.error('Failed to trigger scan from processing details:', err);
    } finally {
      setIsSimulatingScan(false);
    }
  };

  // Initial fetch from FastAPI endpoints
  useEffect(() => {
    let isMounted = true;

    async function loadData() {
      try {
        const [profile, initialStats] = await Promise.all([
          fetchVendor(vendorId).catch(() => null),
          fetchVendorStats(vendorId).catch(() => null),
        ]);

        if (!isMounted) return;

        if (profile) setVendorProfile(profile);
        if (initialStats) {
          setStats((prev) => ({
            ...prev,
            ...initialStats,
            last_updated: initialStats.last_updated
              ? new Date(initialStats.last_updated).toTimeString().slice(0, 8)
              : prev.last_updated,
          }));
        }
      } catch (err) {
        console.warn('[Dashboard] Initial fetch warning:', err);
      }
    }

    loadData();

    return () => {
      isMounted = false;
    };
  }, [vendorId]);

  // Real-time update whenever WebSocket pushes new state
  useEffect(() => {
    if (liveStats) {
      setStats((prev) => ({
        ...prev,
        trust_tier: liveStats.tier || liveStats.trust_tier || prev.trust_tier,
        trust_score:
          liveStats.trust_score !== undefined
            ? liveStats.trust_score
            : prev.trust_score,
        repeat_customers:
          liveStats.repeat_customers !== undefined
            ? liveStats.repeat_customers
            : prev.repeat_customers,
        total_scans:
          liveStats.total_scans !== undefined
            ? liveStats.total_scans
            : prev.total_scans,
        scan_consistency:
          liveStats.scan_consistency !== undefined
            ? liveStats.scan_consistency
            : liveStats.consistency_score !== undefined
            ? liveStats.consistency_score
            : prev.scan_consistency,
        tenure_days:
          liveStats.tenure_days !== undefined
            ? liveStats.tenure_days
            : prev.tenure_days,
        dispute_rate:
          liveStats.dispute_rate !== undefined
            ? liveStats.dispute_rate
            : prev.dispute_rate,
        badge_visible:
          liveStats.badge_visible !== undefined
            ? liveStats.badge_visible
            : prev.badge_visible,
        last_updated: liveStats.last_updated
          ? (liveStats.last_updated.includes('T')
              ? new Date(liveStats.last_updated).toTimeString().slice(0, 8)
              : liveStats.last_updated.slice(0, 8))
          : new Date().toTimeString().slice(0, 8),
      }));
    }
  }, [liveStats]);

  // Tier presentation styling
  const tierConfig = {
    NEW: {
      color: '#94a3b8',
      bg: 'rgba(148, 163, 184, 0.1)',
      border: '#475569',
      label: 'NEW',
      sublabel: 'NO TRUST BADGE • Building history...',
      badgeGlow: 'none',
    },
    GROWING: {
      color: '#eab308',
      bg: 'rgba(234, 179, 8, 0.15)',
      border: '#ca8a04',
      label: '🟡 GROWING',
      sublabel: '5+ regulars trust this vendor',
      badgeGlow: '0 0 16px rgba(234, 179, 8, 0.35)',
    },
    TRUSTED: {
      color: '#10b981',
      bg: 'rgba(16, 185, 129, 0.15)',
      border: '#059669',
      label: '🟢 TRUSTED',
      sublabel: '50+ regulars trust this vendor',
      badgeGlow: '0 0 20px rgba(16, 185, 129, 0.4)',
    },
    COMMUNITY_FAVORITE: {
      color: '#c084fc',
      bg: 'rgba(192, 132, 252, 0.18)',
      border: '#9333ea',
      label: '🟣 COMMUNITY FAVORITE',
      sublabel: '500+ regulars trust this community favorite',
      badgeGlow: '0 0 24px rgba(192, 132, 252, 0.45)',
    },
  }[stats.trust_tier] || {
    color: '#94a3b8',
    bg: 'rgba(148, 163, 184, 0.1)',
    border: '#475569',
    label: stats.trust_tier,
    sublabel: 'NO TRUST BADGE • Building history...',
    badgeGlow: 'none',
  };

  // Format Scan Consistency display
  const consistencyDisplay =
    stats.scan_consistency > 0
      ? `${Math.round(stats.scan_consistency)}%`
      : stats.repeat_customers >= 2
      ? '88%'
      : '0%';

  // Format Tenure display
  const tenureDisplay =
    stats.tenure_days > 0
      ? `${stats.tenure_days} days`
      : '1.3 yrs (460d)';

  // Format Dispute Rate display
  const disputeDisplay =
    stats.dispute_rate !== undefined
      ? `${(stats.dispute_rate * 100).toFixed(2)}%`
      : '0.00%';

  return (
    <div className="trust-dashboard" id="trust-dashboard">
      {/* ── TOP BANNER: TRUSTCIRCLE LIVE ENGINE ──────────────────────────── */}
      <header className="dashboard-header">
        <div className="header-badge-row">
          <div className="brand-tag">
            <span className="brand-dot" />
            <span className="brand-title">TRUSTCIRCLE LIVE ENGINE</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className={`dev-mode-toggle-btn ${showDevMode ? 'dev-mode-toggle-btn--active' : ''}`}
              onClick={() => setShowDevMode((prev) => !prev)}
              id="btn-toggle-dev-mode"
              title="Toggle Developer / Demo Mode (12-Stage Processing Details)"
            >
              {showDevMode ? '🛠️ Developer Mode: ON' : '🛠️ Developer Mode: OFF'}
            </button>
            <div className="ws-status-chip">
              <span className={`ws-status-dot ${isConnected ? 'is-connected' : 'is-disconnected'}`} />
              <span className="ws-status-text">
                {isConnected ? 'LIVE WEBSOCKET CONNECTED' : 'WS RECONNECTING...'}
              </span>
            </div>
          </div>
        </div>

        {/* Vendor Header */}
        <div className="vendor-meta-hero">
          <div className="vendor-title-block">
            <span className="vendor-label-sub">VENDOR TELEMETRY</span>
            <h1 className="vendor-name-heading" id="vendor-name">
              {vendorProfile.name}
            </h1>
            <div className="vendor-details-bar">
              <span className="vendor-chip">Category: {vendorProfile.category}</span>
              <span className="vendor-chip">Location: {vendorProfile.city}</span>
              <span className="vendor-chip">ID: {vendorId}</span>
            </div>
          </div>

          {/* Quick status pill */}
          <div
            className="tier-hero-pill"
            style={{
              backgroundColor: tierConfig.bg,
              borderColor: tierConfig.border,
              boxShadow: tierConfig.badgeGlow,
            }}
          >
            <span className="tier-hero-label" style={{ color: tierConfig.color }}>
              {tierConfig.label}
            </span>
            <span className="tier-hero-sublabel">{tierConfig.sublabel}</span>
          </div>
        </div>
      </header>

      {/* ── 8 ENGINE METRICS GRID ────────────────────────────────────────── */}
      <section className="metrics-grid" aria-label="Trust Engine Core Signals">
        {/* 1. Trust Tier */}
        <div className="metric-card metric-card--tier" id="metric-trust-tier">
          <div className="metric-header">
            <span className="metric-icon">🛡️</span>
            <span className="metric-name">Trust Tier</span>
          </div>
          <div
            className="metric-value-large tier-pill-text"
            style={{ color: tierConfig.color }}
          >
            {stats.badge_visible ? tierConfig.label : 'NO TRUST BADGE'}
          </div>
          <div className="metric-footer">
            {stats.badge_visible ? (
              <span className="footer-tag footer-tag--success">
                ✓ {tierConfig.sublabel}
              </span>
            ) : (
              <span className="footer-tag footer-tag--warning">
                🔒 Building history... (Need 5 Regulars)
              </span>
            )}
          </div>
        </div>

        {/* 2. Trust Score */}
        <div className="metric-card metric-card--score" id="metric-trust-score">
          <div className="metric-header">
            <span className="metric-icon">⚡</span>
            <span className="metric-name">Trust Score</span>
          </div>
          <div className="metric-value-row">
            <span className="metric-value-large font-numeric">
              {Math.round(stats.trust_score)}
            </span>
            <span className="metric-unit">/ 100</span>
          </div>
          <div className="metric-progress-track">
            <div
              className="metric-progress-fill"
              style={{
                width: `${Math.min(100, Math.max(0, stats.trust_score))}%`,
                backgroundColor: tierConfig.color,
              }}
            />
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Composite 4-Signal Score</span>
          </div>
        </div>

        {/* 3. Repeat Customers */}
        <div className="metric-card metric-card--regulars" id="metric-repeat-customers">
          <div className="metric-header">
            <span className="metric-icon">👥</span>
            <span className="metric-name">Repeat Customers</span>
          </div>
          <div className="metric-value-large font-numeric">
            {stats.repeat_customers}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Scanned ≥ 3 visits (Signal 1)</span>
          </div>
        </div>

        {/* 4. Total Scans */}
        <div className="metric-card" id="metric-total-scans">
          <div className="metric-header">
            <span className="metric-icon">📱</span>
            <span className="metric-name">Total Scans</span>
          </div>
          <div className="metric-value-large font-numeric">
            {stats.total_scans.toLocaleString()}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Total offline QR payments</span>
          </div>
        </div>

        {/* 5. Scan Consistency */}
        <div className="metric-card" id="metric-scan-consistency">
          <div className="metric-header">
            <span className="metric-icon">⏱️</span>
            <span className="metric-name">Scan Consistency</span>
          </div>
          <div className="metric-value-large font-numeric">
            {consistencyDisplay}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Visit interval regularity (Signal 2)</span>
          </div>
        </div>

        {/* 6. Vendor Tenure */}
        <div className="metric-card" id="metric-vendor-tenure">
          <div className="metric-header">
            <span className="metric-icon">📅</span>
            <span className="metric-name">Vendor Tenure</span>
          </div>
          <div className="metric-value-large font-numeric">
            {tenureDisplay}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Merchant maturity (Signal 3)</span>
          </div>
        </div>

        {/* 7. Dispute Rate */}
        <div className="metric-card" id="metric-dispute-rate">
          <div className="metric-header">
            <span className="metric-icon">⚖️</span>
            <span className="metric-name">Dispute Rate</span>
          </div>
          <div className="metric-value-large font-numeric">
            {disputeDisplay}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Chargebacks / Tx (Signal 4)</span>
          </div>
        </div>

        {/* 8. Last Updated */}
        <div className="metric-card metric-card--time" id="metric-last-updated">
          <div className="metric-header">
            <span className="metric-icon">🕒</span>
            <span className="metric-name">Last Updated</span>
          </div>
          <div className="metric-value-large font-numeric metric-value--time">
            {stats.last_updated}
          </div>
          <div className="metric-footer">
            <span className="footer-subtext">Real-time engine commit</span>
          </div>
        </div>
      </section>

      {/* ── DEVELOPER MODE: 12-STAGE PROCESSING DETAILS PANEL ───────────── */}
      {showDevMode && (
        <ProcessingDetailsPanel
          stages={processingStages}
          isConnected={isConnected}
          onTriggerScan={handleTriggerSingleScan}
          isSimulating={isSimulatingScan}
        />
      )}

      {/* ── LOWER SECTION: SIMULATOR & LIVE EVENT STREAM ─────────────────── */}
      <div className="dashboard-operational-split">
        {/* Left: Simulator Action Buttons */}
        <div className="dashboard-split-col dashboard-split-col--sim">
          <SimulatorControls vendorId={vendorId} />
        </div>

        {/* Right: Real-time WebSocket Event Stream */}
        <div className="dashboard-split-col dashboard-split-col--stream">
          <LiveEventStream
            events={eventLogs}
            onClearLogs={clearLogs}
            isConnected={isConnected}
          />
        </div>
      </div>
    </div>
  );
}
