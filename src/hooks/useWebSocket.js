// src/hooks/useWebSocket.js - Custom hook for WebSocket communication
// Connects to ws://localhost:8765, exponential backoff reconnect (2s -> 4s -> 8s -> cap 30s)
// Exposes: { sendMessage, connectionStatus }

import { useEffect, useRef, useState, useCallback } from 'react';
import { RECONNECT_BASE_MS, RECONNECT_MAX_MS } from '../constants/config';
import { RECV } from '../constants/wsEvents';

/**
 * useWebSocket - connects once on mount, auto-reconnects on disconnect.
 *
 * @param {string} url - WebSocket URL (ws://localhost:8765)
 * @param {Object} handlers - event callbacks:
 *   onStreamChunk(event)  - jarvis_stream_chunk: { text, done }
 *   onSurface(event)      - jarvis_surface: { bullets[], file }
 *   onModeAck(event)      - jarvis_mode_ack: { mode }
 *   onError(event)        - jarvis_error: { message }
 *
 * @returns {{ sendMessage: Function, connectionStatus: string }}
 */
export default function useWebSocket(url, handlers = {}) {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const handlersRef = useRef(handlers);
  const mountedRef = useRef(true);

  useEffect(() => {
    handlersRef.current = handlers;
  });

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionStatus('connecting');
    console.log('[WS] Connecting to', url);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      reconnectAttemptsRef.current = 0;
      setConnectionStatus('connected');
      console.log('[WS] Connected');
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;

      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.warn('[WS] Malformed JSON received:', event.data);
        return;
      }

      const h = handlersRef.current;
      switch (data.event) {
        case RECV.STREAM_CHUNK:
          h.onStreamChunk?.(data);
          break;

        case RECV.SURFACE:
          h.onSurface?.(data);
          break;

        case RECV.MODE_ACK:
          h.onModeAck?.(data);
          break;

        case RECV.ERROR:
          h.onError?.(data);
          break;

        case RECV.REPORT_GENERATED:
          h.onReportGenerated?.(data);
          break;

        case RECV.STATUS_UPDATE:
          h.onStatusUpdate?.(data);
          break;

        case RECV.TOOL_CALL_STATUS:
          h.onToolCallStatus?.(data);
          break;

        case RECV.PROJECT_PATH_ACK:
          h.onProjectPathAck?.(data);
          break;

        default:
          console.warn('[WS] Unknown event:', data.event, data);
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      setConnectionStatus('disconnected');
      console.log('[WS] Disconnected (code:', event.code, ')');
      wsRef.current = null;

      const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttemptsRef.current, RECONNECT_MAX_MS);
      reconnectAttemptsRef.current += 1;
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})...`);
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = (error) => {
      console.warn('[WS] Error:', error.message || 'WebSocket error');
    };
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendMessage = useCallback((payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
      console.log('[WS] Sent:', payload.event);
    } else {
      console.warn('[WS] Cannot send - not connected. Payload:', payload.event);
    }
  }, []);

  return { sendMessage, connectionStatus };
}
