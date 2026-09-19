/**
 * components/LiveEventStream.jsx
 * ------------------------------
 * Live processing event stream displaying backend pipeline events in real time.
 * Designed to demonstrate to judges that trust calculation is executed asynchronously
 * by the backend rather than computed statically on the client.
 */

import React, { useState } from 'react';

const STAGE_CONFIG = {
  SCAN_RECEIVED: {
    label: 'SCAN_RECEIVED',
    category: 'Ingestion',
    color: '#00d2ff',
    icon: '📥',
    description: 'Offline QR scan payload received by FastAPI gateway',
  },
  SCAN_STORED: {
    label: 'SCAN_STORED',
    category: 'Persistence',
    color: '#3b82f6',
    icon: '💾',
    description: 'Scan document appended to MongoDB scan_events collection',
  },
  AGGREGATION_UPDATED: {
    label: 'AGGREGATION_UPDATED',
    category: 'Analytics',
    color: '#818cf8',
    icon: '📊',
    description: 'MongoDB aggregation grouped unique & repeat customer visits',
  },
  TRUST_CALCULATED: {
    label: 'TRUST_CALCULATED',
    category: 'Trust Engine',
    color: '#fbbf24',
    icon: '⚙️',
    description: 'Statistical Trust Engine calculated composite trust score & tier',
  },
  PRIVACY_CHECKED: {
    label: 'PRIVACY_CHECKED',
    category: 'Privacy Gate',
    color: '#c084fc',
    icon: '🔒',
    description: 'K-anonymity evaluated (k ≥ 5) to prevent customer deanonymization',
  },
  BADGE_UPDATED: {
    label: 'BADGE_UPDATED',
    category: 'State Commit',
    color: '#34d399',
    icon: '🛡️',
    description: 'New trust badge & aggregated stats committed to database',
  },
  TRUST_UPDATED: {
    label: 'TRUST_UPDATED',
    category: 'WebSocket',
    color: '#10b981',
    icon: '⚡',
    description: 'Aggregated trust state broadcasted to all active WebSocket clients',
  },
  DEMO_RESET: {
    label: 'DEMO_RESET',
    category: 'System',
    color: '#f87171',
    icon: '🔄',
    description: 'Vendor state cleared to NEW tier baseline',
  },
};

const ORDERED_PIPELINE_STAGES = [
  'SCAN_RECEIVED',
  'SCAN_STORED',
  'AGGREGATION_UPDATED',
  'TRUST_CALCULATED',
  'PRIVACY_CHECKED',
  'BADGE_UPDATED',
];

export default function LiveEventStream({
  events = [],
  onClearLogs,
  isConnected = true,
}) {
  const [filterStage, setFilterStage] = useState('ALL');

  // Determine currently active or most recent pipeline stage
  const latestStage = events[0]?.stage || null;

  const filteredEvents = filterStage === 'ALL'
    ? events
    : events.filter((e) => e.stage === filterStage);

  return (
    <div className="stream-card" id="live-event-stream">
      {/* Stream Header */}
      <div className="stream-header">
        <div className="stream-title-group">
          <div className="stream-live-indicator">
            <span className={`live-radar-dot ${isConnected ? 'is-live' : 'is-offline'}`} />
            <span className="live-radar-text">
              {isConnected ? 'LIVE WEBSOCKET STREAM' : 'SOCKET RECONNECTING...'}
            </span>
          </div>
          <h3 className="stream-title">Backend Event Stream</h3>
        </div>

        <div className="stream-actions">
          <span className="stream-count-badge">
            {events.length} {events.length === 1 ? 'event' : 'events'}
          </span>
          {events.length > 0 && onClearLogs && (
            <button
              type="button"
              className="stream-clear-btn"
              onClick={onClearLogs}
              title="Clear event history"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Visual Pipeline Stepper Diagram */}
      <div className="pipeline-stepper" aria-label="Processing Pipeline Stages">
        <div className="pipeline-stepper-label">PROCESSING PIPELINE ARCHITECTURE</div>
        <div className="pipeline-steps-track">
          {ORDERED_PIPELINE_STAGES.map((stg, index) => {
            const config = STAGE_CONFIG[stg];
            const isActive = latestStage === stg;
            const hasPassed = events.some((e) => e.stage === stg);

            return (
              <React.Fragment key={stg}>
                <div
                  className={`pipeline-step-node ${isActive ? 'is-active' : ''} ${hasPassed ? 'has-fired' : ''}`}
                  title={`${stg}: ${config?.description}`}
                >
                  <div className="step-node-bubble">
                    <span className="step-node-icon">{config?.icon}</span>
                    <span className="step-node-index">{index + 1}</span>
                  </div>
                  <span className="step-node-name">{stg}</span>
                </div>
                {index < ORDERED_PIPELINE_STAGES.length - 1 && (
                  <div
                    className={`pipeline-step-connector ${hasPassed ? 'is-lit' : ''}`}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Stream Items List */}
      <div className="stream-body">
        {events.length === 0 ? (
          <div className="stream-empty-state">
            <div className="stream-empty-icon">⚡</div>
            <div className="stream-empty-title">Awaiting Live Backend Pipeline Events</div>
            <p className="stream-empty-text">
              Click <strong>[ +1 Scan ]</strong> or any simulator button above.
              FastAPI will execute the 7-stage trust pipeline and stream each stage over WebSocket in real time.
            </p>
          </div>
        ) : (
          <div className="stream-list">
            {filteredEvents.map((evt, idx) => {
              const stageKey = evt.stage || 'SCAN_RECEIVED';
              const cfg = STAGE_CONFIG[stageKey] || {
                label: stageKey,
                category: 'Pipeline',
                color: '#38bdf8',
                icon: '▶',
                description: 'Processing stage complete',
              };

              // Extract readable message or details
              const displayMsg =
                evt.message ||
                evt.data?.message ||
                cfg.description;

              return (
                <div
                  key={`${evt.timestamp}-${idx}`}
                  className="stream-item"
                  style={{ borderLeftColor: cfg.color }}
                >
                  <div className="stream-item-top">
                    <span className="stream-time" title="Event timestamp">
                      {evt.timestamp}
                    </span>
                    <span
                      className="stream-stage-tag"
                      style={{
                        backgroundColor: `${cfg.color}1a`,
                        color: cfg.color,
                        borderColor: `${cfg.color}4d`,
                      }}
                    >
                      <span className="stream-stage-icon">{cfg.icon}</span>
                      {cfg.label}
                    </span>
                  </div>

                  <div className="stream-item-desc">{displayMsg}</div>

                  {/* Contextual metadata pills */}
                  {evt.data && Object.keys(evt.data).length > 0 && (
                    <div className="stream-item-meta">
                      {evt.data.trust_score !== undefined && (
                        <span className="stream-meta-pill">
                          Score: <strong>{evt.data.trust_score}</strong>
                        </span>
                      )}
                      {evt.data.tier && (
                        <span className="stream-meta-pill">
                          Tier: <strong>{evt.data.tier}</strong>
                        </span>
                      )}
                      {evt.data.repeat_customers !== undefined && (
                        <span className="stream-meta-pill">
                          Regulars: <strong>{evt.data.repeat_customers}</strong>
                        </span>
                      )}
                      {evt.data.total_scans !== undefined && (
                        <span className="stream-meta-pill">
                          Total Scans: <strong>{evt.data.total_scans}</strong>
                        </span>
                      )}
                      {evt.data.k_anonymity_floor !== undefined && (
                        <span className="stream-meta-pill">
                          K-Floor: <strong>{evt.data.k_anonymity_floor}</strong>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
