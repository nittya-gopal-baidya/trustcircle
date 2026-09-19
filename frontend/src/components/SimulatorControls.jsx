/**
 * components/SimulatorControls.jsx
 * --------------------------------
 * Hackathon 1-Click Simulation Controls:
 *   - [ Reset Demo ]                     -> Clean baseline: repeat=0, NEW, NO TRUST BADGE
 *   - [ Simulate 5 Repeat Customers ]     -> NEW -> 🟡 GROWING (5+ regulars)
 *   - [ Simulate 45 More Repeat Customers]-> GROWING -> 🟢 TRUSTED (50+ regulars)
 *   - [ +1 Live Scan ]                    -> Live walk-in 7-stage pipeline demonstration
 */

import React, { useState } from 'react';
import {
  triggerSingleScanSimulation,
  triggerBurstSimulation,
  resetSimulation,
} from '../services/api';

export default function SimulatorControls({
  vendorId = 'sharma_chai_001',
  onActionTriggered,
}) {
  const [activeAction, setActiveAction] = useState(null);
  const [feedback, setFeedback] = useState(null);

  const runAction = async (actionKey, label, apiFn) => {
    if (activeAction) return;
    setActiveAction(actionKey);
    setFeedback({ type: 'info', text: `Triggering: ${label}...` });

    try {
      const result = await apiFn();
      setFeedback({
        type: 'success',
        text: result.message || `${label} processed successfully!`,
      });
      if (onActionTriggered) {
        onActionTriggered({ action: actionKey, result });
      }
    } catch (err) {
      console.error(`Simulator error (${actionKey}):`, err);
      setFeedback({
        type: 'error',
        text: `Error: ${err.message || 'Simulation call failed'}`,
      });
    } finally {
      setActiveAction(null);
    }
  };

  const handleReset = () =>
    runAction('reset', 'Reset Demo', () => resetSimulation(vendorId));

  const handleBurst5 = () =>
    runAction('burst_5', 'Simulate 5 Repeat Customers', () =>
      triggerBurstSimulation({ vendor_id: vendorId, customers: 5 })
    );

  const handleBurst45 = () =>
    runAction('burst_45', 'Simulate 45 More Repeat Customers', () =>
      triggerBurstSimulation({ vendor_id: vendorId, customers: 45 })
    );

  const handleSingleScan = () =>
    runAction('scan', '+1 Live Scan', () =>
      triggerSingleScanSimulation({ vendor_id: vendorId, amount: 20.0 })
    );

  return (
    <div className="sim-panel" id="simulator-controls">
      <div className="sim-panel-header">
        <div className="sim-title-group">
          <span className="sim-chip">1-CLICK HACKATHON DEMO</span>
          <h3 className="sim-title">Live Behavior Simulator</h3>
        </div>
        <div className="sim-legend">
          Demonstrates progressive tier transitions directly computed by backend Trust Engine
        </div>
      </div>

      <div className="sim-buttons-grid">
        {/* Step 0: Reset Demo */}
        <button
          type="button"
          id="btn-sim-reset"
          className={`sim-btn sim-btn--reset ${activeAction === 'reset' ? 'is-loading' : ''}`}
          onClick={handleReset}
          disabled={!!activeAction}
          title="Resets vendor to initial baseline: 0 repeat customers, NEW tier, badge hidden"
        >
          <div className="sim-btn-icon">🔄</div>
          <div className="sim-btn-body">
            <span className="sim-btn-label">Reset Demo</span>
            <span className="sim-btn-desc">Initial: repeat=0 • NEW • NO TRUST BADGE</span>
          </div>
          {activeAction === 'reset' && <span className="sim-spinner" />}
        </button>

        {/* Step 1: Simulate 5 Repeat Customers (NEW -> GROWING) */}
        <button
          type="button"
          id="btn-sim-burst-5"
          className={`sim-btn sim-btn--sky ${activeAction === 'burst_5' ? 'is-loading' : ''}`}
          onClick={handleBurst5}
          disabled={!!activeAction}
          title="Simulates 5 repeat customers. Unlocks K-anonymity privacy floor into GROWING tier."
        >
          <div className="sim-btn-icon">🟡</div>
          <div className="sim-btn-body">
            <span className="sim-btn-label">Simulate 5 Repeat Customers</span>
            <span className="sim-btn-desc">NEW → 🟡 GROWING (5+ regulars trust this vendor)</span>
          </div>
          {activeAction === 'burst_5' && <span className="sim-spinner" />}
        </button>

        {/* Step 2: Simulate 45 More Repeat Customers (GROWING -> TRUSTED) */}
        <button
          type="button"
          id="btn-sim-burst-45"
          className={`sim-btn sim-btn--emerald ${activeAction === 'burst_45' ? 'is-loading' : ''}`}
          onClick={handleBurst45}
          disabled={!!activeAction}
          title="Simulates 45 more repeat customers. Crosses the 50 regular threshold into TRUSTED tier."
        >
          <div className="sim-btn-icon">🟢</div>
          <div className="sim-btn-body">
            <span className="sim-btn-label">Simulate 45 More Repeat Customers</span>
            <span className="sim-btn-desc">GROWING → 🟢 TRUSTED (50+ regulars trust this vendor)</span>
          </div>
          {activeAction === 'burst_45' && <span className="sim-spinner" />}
        </button>

        {/* Step 3: Single Walk-in Scan */}
        <button
          type="button"
          id="btn-sim-single-scan"
          className={`sim-btn sim-btn--cyan ${activeAction === 'scan' ? 'is-loading' : ''}`}
          onClick={handleSingleScan}
          disabled={!!activeAction}
          title="Fires 1 live scan through the full 7-stage processing pipeline"
        >
          <div className="sim-btn-icon">⚡</div>
          <div className="sim-btn-body">
            <span className="sim-btn-label">+1 Live Scan</span>
            <span className="sim-btn-desc">Single walk-in payment (7-stage pipeline)</span>
          </div>
          {activeAction === 'scan' && <span className="sim-spinner" />}
        </button>
      </div>

      {/* Simulator Response Feedback */}
      {feedback && (
        <div className={`sim-feedback sim-feedback--${feedback.type}`}>
          <span className="sim-feedback-icon">
            {feedback.type === 'success' ? '✓' : feedback.type === 'error' ? '⚠' : 'ℹ'}
          </span>
          <span className="sim-feedback-text">{feedback.text}</span>
        </div>
      )}
    </div>
  );
}
