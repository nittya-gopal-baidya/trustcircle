/**
 * components/TrustBadge.jsx
 * -------------------------
 * TrustCircle live verified trust badge.
 *
 * Rules:
 *   - Fetches & receives live updates from FastAPI backend via WebSocket
 *   - NEVER hardcodes tier or regulars count
 *   - When badge_visible === false:
 *       Displays "TrustCircle badge not available yet"
 *       Never reveals exact counts below 5
 *   - When badge_visible === true:
 *       Displays thresholded social proof based on tier:
 *       "5+ regulars trust this vendor" (GROWING)
 *       "50+ regulars trust this vendor" (TRUSTED)
 *       "500+ regulars trust this vendor" (COMMUNITY_FAVORITE)
 */

import React from 'react';

export default function TrustBadge({ badge, isLive, isLoading, error }) {
  if (isLoading && !badge) {
    return (
      <div className="trust-badge trust-badge--loading" id="trust-badge-loading">
        <div className="trust-badge__spinner" />
        <span>Verifying TrustCircle credentials...</span>
      </div>
    );
  }

  if (error && !badge) {
    return (
      <div className="trust-badge trust-badge--inactive" id="trust-badge-error">
        <div className="trust-badge__content">
          <div className="trust-badge__primary-text">Connecting to TrustCircle...</div>
          <div className="trust-badge__secondary-text">{error}</div>
        </div>
      </div>
    );
  }

  if (!badge) {
    return (
      <div className="trust-badge trust-badge--inactive" id="trust-badge-empty">
        <div className="trust-badge__content">
          <div className="trust-badge__primary-text">NO TRUST BADGE</div>
          <div className="trust-badge__secondary-text">Building history...</div>
        </div>
      </div>
    );
  }

  const isVisible = Boolean(badge.badge_visible);
  const tier = (badge.tier || badge.trust_tier || 'NEW').toUpperCase();

  // ── CASE 1: PRIVACY GATED / NOT VISIBLE YET ──────────────────────────────
  if (!isVisible) {
    return (
      <div className="trust-badge trust-badge--inactive" id="trust-badge-container">
        <div className="trust-badge__icon-wrapper">
          <svg
            className="trust-badge__icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
          </svg>
        </div>
        <div className="trust-badge__content">
          <div className="trust-badge__primary-text">
            NO TRUST BADGE
          </div>
          <div className="trust-badge__secondary-text">
            Building history...
          </div>
        </div>
        {isLive && (
          <div className="trust-badge__live-indicator" title="Connected to live trust stream">
            <span className="trust-badge__live-dot" />
            <span className="trust-badge__live-label">LIVE</span>
          </div>
        )}
      </div>
    );
  }

  // ── CASE 2: VISIBLE TRUST BADGE (GROWING / TRUSTED / COMMUNITY_FAVORITE) ───

  // Compute tier-specific threshold message dynamically
  let thresholdMessage = badge.message;
  if (!thresholdMessage || thresholdMessage === 'Building history...') {
    if (tier === 'GROWING') {
      thresholdMessage = '5+ regulars trust this vendor';
    } else if (tier === 'TRUSTED') {
      thresholdMessage = '50+ regulars trust this vendor';
    } else if (tier === 'COMMUNITY_FAVORITE') {
      thresholdMessage = '500+ regulars trust this vendor';
    } else {
      thresholdMessage = 'Verified merchant';
    }
  }

  // Tier metadata
  const tierConfig = {
    GROWING: {
      className: 'trust-badge--growing',
      badgeLabel: '🟡 GROWING',
      accentColor: '#eab308',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="M12 8v8" />
          <path d="M8 12l4-4 4 4" />
        </svg>
      ),
    },
    TRUSTED: {
      className: 'trust-badge--trusted',
      badgeLabel: '🟢 TRUSTED',
      accentColor: '#10b981',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      ),
    },
    COMMUNITY_FAVORITE: {
      className: 'trust-badge--community',
      badgeLabel: '🟣 COMMUNITY FAVORITE',
      accentColor: '#a855f7',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
        </svg>
      ),
    },
  };

  const currentConfig = tierConfig[tier] || tierConfig.TRUSTED;

  return (
    <div
      className={`trust-badge ${currentConfig.className}`}
      id="trust-badge-container"
      data-tier={tier}
    >
      <div className="trust-badge__icon-wrapper">
        {currentConfig.icon}
      </div>

      <div className="trust-badge__content">
        <div className="trust-badge__header-line">
          <span className="trust-badge__tier-name">{currentConfig.badgeLabel}</span>
          <span className="trust-badge__verified-tag">✓ VERIFIED</span>
        </div>

        <div className="trust-badge__threshold-message">
          {thresholdMessage}
        </div>

        {badge.total_scans_approx && (
          <div className="trust-badge__meta-line">
            <span>{badge.total_scans_approx} scans</span>
            {badge.tenure_days && (
              <>
                <span className="trust-badge__meta-dot">•</span>
                <span>{Math.max(1, Math.round(badge.tenure_days / 30))} mos on Paytm</span>
              </>
            )}
          </div>
        )}
      </div>

      {isLive && (
        <div className="trust-badge__live-indicator" title="Connected to real-time Trust Engine">
          <span className="trust-badge__live-dot" />
          <span className="trust-badge__live-label">LIVE</span>
        </div>
      )}
    </div>
  );
}
