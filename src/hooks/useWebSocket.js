// src/hooks/useWebSocket.js — Custom hook for WebSocket communication
// Connects to ws://localhost:8765, flat 2s reconnect, centralized event handling
// Exposes: { sendMessage, connectionStatus }

import { useEffect, useRef, useState, useCallback } from 'react';

// ─── Reconnect config ─────────────────────────────────────
const RECONNECT_DELAY_MS = 2000; // Flat 2s — no exponential, backend restarts constantly

/**
 * useWebSocket — connects once on mount, auto-reconnects on disconnect.
 *
 * @param {string} url — WebSocket URL (ws://localhost:8765)
 * @param {Object} handlers — event callbacks:
 *   onStreamChunk(event)  — jarvis_stream_chunk: { text, done }
 *   onResponse(event)     — jarvis_response: { text }
 *   onSurface(event)      — jarvis_surface: { bullets[], file }
 *   onModeAck(event)      — jarvis_mode_ack: { mode }
 *   onError(event)        — jarvis_error: { message }
 *
 * @returns {{ sendMessage: Function, connectionStatus: string }}
 */
export default function useWebSocket(url, handlers = {}) {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const handlersRef = useRef(handlers);
  const mountedRef = useRef(true);

  // Keep handlers ref current without re-triggering effect
  useEffect(() => {
    handlersRef.current = handlers;
  });

  /**
   * Connect to WebSocket server.
   * Called on mount and after each disconnection (with 2s delay).
   */
  const connect = useCallback(() => {
    // Don't connect if already connected or component unmounted
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionStatus('connecting');
    console.log('[WS] Connecting to', url);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    // ─── Connected ──────────────────────────────────────
    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnectionStatus('connected');
      console.log('[WS] Connected');
    };

    // ─── Message received ───────────────────────────────
    ws.onmessage = (event) => {
      if (!mountedRef.current) return;

      // All JSON.parse calls wrapped in try/catch — never crash on malformed payloads
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.warn('[WS] Malformed JSON received:', event.data);
        return;
      }

      // ─── Centralized inbound event switch ─────────────
      // One place to update if the contract changes
      const h = handlersRef.current;
      switch (data.type) {
        case 'jarvis_stream_chunk':
          h.onStreamChunk?.(data);
          break;

        case 'jarvis_response':
          h.onResponse?.(data);
          break;

        case 'jarvis_surface':
          h.onSurface?.(data);
          break;

        case 'jarvis_mode_ack':
          h.onModeAck?.(data);
          break;

        case 'jarvis_error':
          h.onError?.(data);
          break;

        default:
          console.warn('[WS] Unknown event type:', data.type);
      }
    };

    // ─── Disconnected — schedule reconnect ──────────────
    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      setConnectionStatus('disconnected');
      console.log('[WS] Disconnected (code:', event.code, ')');
      wsRef.current = null;

      // Auto-reconnect with flat 2s delay
      reconnectTimerRef.current = setTimeout(() => {
        console.log('[WS] Reconnecting...');
        connect();
      }, RECONNECT_DELAY_MS);
    };

    // ─── Error — log but don't crash ────────────────────
    ws.onerror = (error) => {
      console.warn('[WS] Error:', error.message || 'WebSocket error');
      // onclose will fire after this, triggering reconnect
    };
  }, [url]);

  // ─── Connect on mount, cleanup on unmount ─────────────
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      // Clean up everything
      mountedRef.current = false;

      // Clear reconnect timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // Close socket
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  // ─── Send message to backend ──────────────────────────
  const sendMessage = useCallback((payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
      console.log('[WS] Sent:', payload.type);
    } else {
      console.warn('[WS] Cannot send — not connected. Payload:', payload.type);
    }
  }, []);

  return { sendMessage, connectionStatus };
}
