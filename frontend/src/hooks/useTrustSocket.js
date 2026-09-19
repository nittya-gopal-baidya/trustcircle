/**
 * hooks/useTrustSocket.js
 * -----------------------
 * Real-time WebSocket hook connecting to:
 *   ws://localhost:8000/ws/vendor/{vendorId}
 *
 * Capabilities:
 *   - Instant React state update on `TRUST_UPDATED` event (no page refresh)
 *   - Automatic reconnection with exponential backoff
 *   - Loading and error states
 *   - Live pipeline stage tracking for hackathon demonstrations
 *   - Zero exposure of customer_hash or PII
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const WS_BASE = 'ws://localhost:8000';

export function useTrustSocket(vendorId = 'sharma_chai_001') {
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [badge, setBadge] = useState(null);
  const [liveStats, setLiveStats] = useState(null);
  const [latestStageEvent, setLatestStageEvent] = useState(null);
  const [eventLogs, setEventLogs] = useState([]);
  const [processingStages, setProcessingStages] = useState([]);

  const wsRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef(null);

  const clearLogs = useCallback(() => {
    setEventLogs([]);
    setLatestStageEvent(null);
  }, []);

  const connect = useCallback(() => {
    if (!vendorId) return;

    // Clear any existing connection before opening new
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null; // Prevent trigger loop
        wsRef.current.close();
      } catch (e) {
        // ignore
      }
    }

    setIsLoading(true);
    setError(null);

    const wsUrl = `${WS_BASE}/ws/vendor/${vendorId}`;
    console.log(`[WS] Connecting to: ${wsUrl}`);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(`[WS] Connected successfully to vendor channel: ${vendorId}`);
        setIsConnected(true);
        setIsLoading(false);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const timeStr = new Date().toTimeString().slice(0, 8); // "20:41:01"

          // ── Handler 0: PROCESSING_DETAILS (12-stage pipeline breakdown) ───
          if (payload.event === 'PROCESSING_DETAILS' && payload.data?.stages) {
            console.log(`[WS] Received PROCESSING_DETAILS (12 stages):`, payload.data.stages);
            setProcessingStages(payload.data.stages);
            return;
          }

          // ── Handler: DEMO_RESET ───────────────────────────────────────────
          if (payload.event === 'DEMO_RESET') {
            console.log(`[WS] Received DEMO_RESET`);
            setProcessingStages([]);
          }

          // ── Handler 1: TRUST_UPDATED event ─────────────────────────────────
          if (payload.event === 'TRUST_UPDATED' && payload.data) {
            console.log(`[WS] Received TRUST_UPDATED:`, payload.data);
            const updated = {
              ...payload.data,
              vendor_id: payload.vendor_id || vendorId,
            };
            setBadge(updated);
            setLiveStats(updated);
            setIsLoading(false);

            // Also record in event log if BADGE_UPDATED wasn't fired just prior
            const stageEvent = {
              stage: 'TRUST_UPDATED',
              vendor_id: payload.vendor_id,
              data: payload.data,
              timestamp: timeStr,
              message: payload.data.message || `Trust state updated: Tier ${payload.data.tier}`,
            };
            setLatestStageEvent(stageEvent);
            setEventLogs((prev) => [stageEvent, ...prev.slice(0, 49)]);
          }
          // ── Handler 2: Raw BadgePayload format ─────────────────────────────
          else if (payload.trust_tier || payload.badge_visible !== undefined) {
            console.log(`[WS] Received BadgePayload:`, payload);
            const badgeObj = {
              ...payload,
              tier: payload.trust_tier || payload.tier,
            };
            setBadge(badgeObj);
            setLiveStats(badgeObj);
            setIsLoading(false);
          }
          // ── Handler 3: Intermediate pipeline stage events ──────────────────
          else if (payload.event) {
            const stageEvent = {
              stage: payload.event,
              vendor_id: payload.vendor_id,
              data: payload.data || {},
              timestamp: timeStr,
              message: payload.data?.message || payload.event,
            };
            setLatestStageEvent(stageEvent);
            setEventLogs((prev) => [stageEvent, ...prev.slice(0, 49)]);
          }
        } catch (parseErr) {
          console.warn('[WS] Message parse error:', parseErr, event.data);
        }
      };

      ws.onclose = (e) => {
        setIsConnected(false);
        console.log(`[WS] Disconnected (code=${e.code}). Attempting reconnect...`);

        // Exponential backoff: min 1s, max 8s
        const backoffMs = Math.min(1000 * Math.pow(1.5, reconnectAttemptsRef.current), 8000);
        reconnectAttemptsRef.current += 1;

        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, backoffMs);
      };

      ws.onerror = (err) => {
        console.warn(`[WS] Socket error:`, err);
        setError('WebSocket error connecting to server');
        setIsConnected(false);
      };
    } catch (createErr) {
      console.error(`[WS] Failed to instantiate WebSocket:`, createErr);
      setError(createErr.message);
      setIsLoading(false);
    }
  }, [vendorId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    isConnected,
    isLoading,
    error,
    badge,
    setBadge,
    liveStats,
    setLiveStats,
    latestStageEvent,
    eventLogs,
    clearLogs,
    processingStages,
    setProcessingStages,
    reconnect: connect,
  };
}
