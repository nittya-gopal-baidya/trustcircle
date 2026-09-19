/**
 * components/PaymentScreen.jsx
 * ----------------------------
 * The primary customer payment confirmation screen.
 *
 * Structure:
 *   - Header with secure UPI branding
 *   - PAY TO: Sharma Chai Corner
 *   - TrustCircle live trust badge
 *   - AMOUNT: ₹40
 *   - [ Pay Securely ] button
 *   - Floating presentation toolbar for demoing live tier transitions
 */

import React, { useState, useEffect } from 'react';
import TrustBadge from './TrustBadge';
import { useTrustSocket } from '../hooks/useTrustSocket';
import {
  fetchVendor,
  fetchVendorBadge,
  submitScan,
  resetSimulation,
  triggerBurstSimulation,
  triggerSingleScanSimulation,
} from '../services/api';

export default function PaymentScreen({ vendorId = 'sharma_chai_001' }) {
  const [vendor, setVendor] = useState({
    name: 'Sharma Chai Corner',
    category: 'Tea Stall',
    city: 'Jaipur',
  });
  const [amount, setAmount] = useState(40);
  const [isProcessingPayment, setIsProcessingPayment] = useState(false);
  const [paymentSuccess, setPaymentSuccess] = useState(false);
  const [demoActionStatus, setDemoActionStatus] = useState('');

  // Real-time WebSocket connection to the vendor channel
  const { isConnected, isLoading, error, badge, setBadge, latestStageEvent } = useTrustSocket(vendorId);

  // Initial load from FastAPI HTTP endpoints
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [vendorData, badgeData] = await Promise.all([
          fetchVendor(vendorId).catch(() => null),
          fetchVendorBadge(vendorId).catch(() => null),
        ]);

        if (vendorData) setVendor(vendorData);
        if (badgeData) setBadge(badgeData);
      } catch (err) {
        console.warn('Initial fetch error:', err);
      }
    }
    loadInitialData();
  }, [vendorId, setBadge]);

  // Handle "Pay Securely" action
  const handlePaySecurely = async () => {
    if (isProcessingPayment) return;
    setIsProcessingPayment(true);
    setDemoActionStatus('Processing payment & verifying trust signal...');

    try {
      // Send simulated scan to backend
      const randomHash = Array.from(crypto.getRandomValues(new Uint8Array(32)))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');

      await submitScan({
        vendor_id: vendorId,
        customer_hash: randomHash,
        amount: Number(amount),
      });

      setPaymentSuccess(true);
      setDemoActionStatus('Payment completed successfully!');
      setTimeout(() => setPaymentSuccess(false), 3500);
    } catch (err) {
      console.error('Payment submission failed:', err);
      setDemoActionStatus('Payment error. Please check server.');
    } finally {
      setIsProcessingPayment(false);
    }
  };

  // Demo helper functions for presentation
  const handleDemoReset = async () => {
    setDemoActionStatus('Resetting demo vendor to clean state...');
    try {
      await resetSimulation(vendorId);
      const newBadge = await fetchVendorBadge(vendorId);
      setBadge(newBadge);
      setDemoActionStatus('Reset complete: Vendor is in NEW tier (badge hidden)');
    } catch (e) {
      setDemoActionStatus('Reset failed: ' + e.message);
    }
  };

  const handleDemoSingleScan = async () => {
    setDemoActionStatus('Simulating single live scan (+1 scan)...');
    try {
      await triggerSingleScanSimulation({ vendor_id: vendorId, amount: 25.0 });
      setDemoActionStatus('Single scan processed through 7 stages!');
    } catch (e) {
      setDemoActionStatus('Scan simulation failed: ' + e.message);
    }
  };

  const handleDemoBurst = async (customers) => {
    setDemoActionStatus(`Simulating +${customers} repeat customers...`);
    try {
      const res = await triggerBurstSimulation({ vendor_id: vendorId, customers });
      setDemoActionStatus(`Added ${customers} customers! New tier: ${res.tier} (${res.repeat_customers_total} repeat)`);
    } catch (e) {
      setDemoActionStatus('Burst simulation failed: ' + e.message);
    }
  };

  return (
    <div className="payment-screen-wrapper">
      {/* ── Demo Presentation Toolbar (Top) ────────────────────────── */}
      <div className="demo-toolbar" id="demo-toolbar">
        <div className="demo-toolbar__status">
          <span className={`connection-pill ${isConnected ? 'connection-pill--online' : 'connection-pill--offline'}`}>
            {isConnected ? '● WebSocket Live' : '○ Connecting...'}
          </span>
          {latestStageEvent && (
            <span className="demo-toolbar__stage-ticker">
              Stage: <strong>{latestStageEvent.stage}</strong>
            </span>
          )}
        </div>

        <div className="demo-toolbar__controls">
          <button className="demo-btn demo-btn--reset" onClick={handleDemoReset} title="Reset to clean state: repeat=0, NEW">
            ↺ Reset Demo
          </button>
          <button className="demo-btn demo-btn--accent" onClick={() => handleDemoBurst(5)} title="Simulate 5 repeat customers (NEW -> GROWING)">
            Simulate 5 Repeat Customers
          </button>
          <button className="demo-btn demo-btn--accent" onClick={() => handleDemoBurst(45)} title="Simulate 45 more repeat customers (GROWING -> TRUSTED)">
            Simulate 45 More Repeat Customers
          </button>
          <button className="demo-btn" onClick={handleDemoSingleScan} title="Simulate 1 walk-in scan">
            +1 Live Scan
          </button>
        </div>
      </div>

      {demoActionStatus && (
        <div className="demo-status-banner">
          {demoActionStatus}
        </div>
      )}

      {/* ── Main Smartphone / Payment Card Frame ───────────────────── */}
      <div className="payment-card-frame" id="payment-card-frame">
        {/* App Top Bar */}
        <div className="payment-header">
          <div className="payment-header__brand">
            <span className="brand-dot" />
            <span className="brand-name">Paytm | TrustCircle</span>
          </div>
          <div className="payment-header__security">
            <svg className="lock-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <span>256-Bit SSL</span>
          </div>
        </div>

        {/* PAY TO Section */}
        <div className="pay-to-section">
          <div className="section-label">PAY TO</div>
          <div className="merchant-details">
            <div className="merchant-avatar">
              <span>{vendor.name ? vendor.name.substring(0, 2).toUpperCase() : 'SC'}</span>
            </div>
            <div className="merchant-meta">
              <h1 className="merchant-name">{vendor.name || 'Sharma Chai Corner'}</h1>
              <div className="merchant-sub">
                <span className="merchant-category">{vendor.category || 'Tea Stall'}</span>
                <span className="meta-sep">•</span>
                <span className="merchant-city">{vendor.city || 'Jaipur'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* TrustCircle Live Badge Component */}
        <div className="badge-placement-area">
          <TrustBadge badge={badge} isLive={isConnected} isLoading={isLoading} error={error} />
        </div>

        {/* AMOUNT Section */}
        <div className="amount-section">
          <div className="section-label">AMOUNT</div>
          <div className="amount-input-container">
            <span className="currency-symbol">₹</span>
            <input
              type="number"
              className="amount-input"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              min="1"
              max="10000"
              id="amount-input"
            />
          </div>

          <div className="quick-amount-chips">
            {[20, 40, 80, 150].map((val) => (
              <button
                key={val}
                type="button"
                className={`amount-chip ${amount === val ? 'amount-chip--active' : ''}`}
                onClick={() => setAmount(val)}
              >
                ₹{val}
              </button>
            ))}
          </div>
        </div>

        {/* Payment Instrument Card */}
        <div className="payment-method-card">
          <div className="payment-method-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
              <line x1="1" y1="10" x2="23" y2="10" />
            </svg>
          </div>
          <div className="payment-method-info">
            <div className="method-title">Paytm Payments Bank Account</div>
            <div className="method-sub">A/c ending in •••• 4092</div>
          </div>
          <div className="payment-method-check">
            <span>✓</span>
          </div>
        </div>

        {/* Pay Securely Button */}
        <div className="payment-action-area">
          <button
            type="button"
            className={`pay-button ${isProcessingPayment ? 'pay-button--loading' : ''} ${paymentSuccess ? 'pay-button--success' : ''}`}
            onClick={handlePaySecurely}
            disabled={isProcessingPayment}
            id="pay-securely-btn"
          >
            {isProcessingPayment ? (
              <span className="button-loader-content">
                <span className="button-spinner" />
                <span>Verifying & Paying...</span>
              </span>
            ) : paymentSuccess ? (
              <span className="button-success-content">
                <span>✓ Payment of ₹{amount} Successful</span>
              </span>
            ) : (
              <span>Pay Securely ₹{amount}</span>
            )}
          </button>
        </div>

        {/* Security & Regulatory Footer */}
        <div className="payment-footer">
          <span>Protected by TrustCircle Social Proof Engine</span>
          <span className="footer-sub">Aggregated repeat-customer verification</span>
        </div>
      </div>
    </div>
  );
}
