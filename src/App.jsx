// src/App.jsx — Minimal root component
// Infrastructure only: WebSocket hook + overlay focus + state management
// YOU build the UI components — this just wires the data

import React, { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import useWebSocket from './hooks/useWebSocket';

// ─── Message reducer ─────────────────────────────────────
// Centralized state management for conversation messages
function messageReducer(state, action) {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return [...state, {
        id: Date.now(),
        role: 'user',
        text: action.text,
        timestamp: new Date(),
      }];

    case 'ADD_JARVIS_MESSAGE':
      return [...state, {
        id: Date.now(),
        role: 'jarvis',
        text: action.text,
        timestamp: new Date(),
      }];

    case 'START_STREAM':
      // Add empty jarvis message that will be built up by chunks
      return [...state, {
        id: action.id || Date.now(),
        role: 'jarvis',
        text: '',
        timestamp: new Date(),
        streaming: true,
      }];

    case 'APPEND_CHUNK':
      // Append text to the last (streaming) message
      return state.map((msg, i) =>
        i === state.length - 1 && msg.streaming
          ? { ...msg, text: msg.text + action.text }
          : msg
      );

    case 'FINISH_STREAM':
      // Mark the streaming message as done
      return state.map((msg, i) =>
        i === state.length - 1 && msg.streaming
          ? { ...msg, streaming: false }
          : msg
      );

    case 'REPLACE_RESPONSE':
      // Replace entire last jarvis message (used during tool-use loops)
      return state.map((msg, i) =>
        i === state.length - 1 && msg.role === 'jarvis'
          ? { ...msg, text: action.text, streaming: false }
          : msg
      );

    case 'ADD_ERROR':
      return [...state, {
        id: Date.now(),
        role: 'error',
        text: action.message,
        timestamp: new Date(),
      }];

    case 'CLEAR':
      return [];

    default:
      return state;
  }
}

/**
 * App — root component with all data wiring.
 * Exposes state + handlers via props or context — build your own UI on top.
 */
export default function App() {
  const [messages, dispatch] = useReducer(messageReducer, []);
  const [isStreaming, setIsStreaming] = useState(false);
  const [mode, setMode] = useState('local');            // 'local' | 'cloud' | 'pending'
  const [surfaceData, setSurfaceData] = useState(null); // { bullets: [], file: string }
  const inputRef = useRef(null);

  // ─── WebSocket ─────────────────────────────────────────
  const { sendMessage, connectionStatus } = useWebSocket('ws://localhost:8765', {
    onStreamChunk: (event) => {
      if (!isStreaming) {
        setIsStreaming(true);
        dispatch({ type: 'START_STREAM' });
      }
      dispatch({ type: 'APPEND_CHUNK', text: event.text });
      if (event.done) {
        dispatch({ type: 'FINISH_STREAM' });
        setIsStreaming(false);
      }
    },
    onResponse: (event) => {
      if (isStreaming) {
        dispatch({ type: 'REPLACE_RESPONSE', text: event.text });
        setIsStreaming(false);
      } else {
        dispatch({ type: 'ADD_JARVIS_MESSAGE', text: event.text });
      }
    },
    onSurface: (event) => {
      setSurfaceData({ bullets: event.bullets, file: event.file });
    },
    onModeAck: (event) => {
      // ONLY now update the mode badge — no optimistic updates
      setMode(event.mode);
    },
    onError: (event) => {
      dispatch({ type: 'ADD_ERROR', message: event.message });
      setIsStreaming(false);
    },
  });

  // ─── Focus input when overlay opens (Ctrl+Space) ──────
  useEffect(() => {
    if (window.jarvis?.onToggleOverlay) {
      return window.jarvis.onToggleOverlay(() => {
        setTimeout(() => inputRef.current?.focus(), 50);
      });
    }
  }, []);

  // ─── Send user message ────────────────────────────────
  const handleSend = useCallback((text) => {
    if (!text.trim() || isStreaming) return;
    dispatch({ type: 'ADD_USER_MESSAGE', text: text.trim() });
    sendMessage({
      type: 'user_query',
      text: text.trim(),
      mode: mode === 'pending' ? 'local' : mode,
    });
  }, [isStreaming, mode, sendMessage]);

  // ─── Toggle mode ──────────────────────────────────────
  const handleModeToggle = useCallback(() => {
    if (mode === 'pending') return;
    const newMode = mode === 'local' ? 'cloud' : 'local';
    setMode('pending'); // Go to PENDING immediately
    sendMessage({ type: 'mode_change', mode: newMode });
    // Stay in PENDING until jarvis_mode_ack arrives — no optimistic update
  }, [mode, sendMessage]);

  // ─── Dismiss surface card ─────────────────────────────
  const handleDismissSurface = useCallback(() => {
    if (surfaceData) {
      sendMessage({ type: 'surface_dismissed', file: surfaceData.file });
      setSurfaceData(null);
    }
  }, [surfaceData, sendMessage]);

  // ─── Surface auto-dismiss (8 seconds) ─────────────────
  useEffect(() => {
    if (!surfaceData) return;
    const timer = setTimeout(() => {
      handleDismissSurface();
    }, 8000);
    return () => clearTimeout(timer); // Clean up on unmount or new surface
  }, [surfaceData, handleDismissSurface]);

  // ════════════════════════════════════════════════════════
  // YOUR UI GOES HERE
  // All the data and handlers are ready — build your components
  //
  // Available state:
  //   messages        — Array<{ id, role, text, timestamp, streaming? }>
  //   isStreaming      — boolean (true while JARVIS is responding)
  //   mode            — 'local' | 'cloud' | 'pending'
  //   connectionStatus — 'connected' | 'disconnected' | 'connecting'
  //   surfaceData     — { bullets: string[], file: string } | null
  //
  // Available handlers:
  //   handleSend(text)       — send a user message
  //   handleModeToggle()     — toggle local/cloud mode
  //   handleDismissSurface() — dismiss the surface card
  //
  // Available refs:
  //   inputRef — attach to your input element for auto-focus on Ctrl+Space
  // ════════════════════════════════════════════════════════

  return (
    <div className="overlay" style={{
      width: '100%',
      height: '100%',
      background: 'rgba(12, 12, 20, 0.95)',
      borderRadius: '16px',
      border: '1px solid rgba(100, 140, 255, 0.1)',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Inter', sans-serif",
      color: '#e8e8f0',
      overflow: 'hidden',
    }}>
      {/* ─── Placeholder: replace with your UI ─────────── */}
      <div style={{ padding: '16px', borderBottom: '1px solid rgba(100,140,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', WebkitAppRegion: 'drag' }}>
        <span style={{ fontSize: '14px', fontWeight: 600, letterSpacing: '1.5px', background: 'linear-gradient(135deg, #00d4ff, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>JARVIS</span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', WebkitAppRegion: 'no-drag' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: connectionStatus === 'connected' ? '#10b981' : connectionStatus === 'connecting' ? '#f59e0b' : '#ef4444' }} title={connectionStatus} />
          <button onClick={handleModeToggle} disabled={mode === 'pending'} style={{ padding: '4px 12px', borderRadius: 20, border: 'none', fontSize: '20px', fontWeight: 700, cursor: 'pointer', background: mode === 'local' ? 'rgba(16,185,129,0.15)' : mode === 'cloud' ? 'rgba(59,130,246,0.15)' : 'rgba(120,120,140,0.15)', color: mode === 'local' ? '#10b981' : mode === 'cloud' ? '#3b82f6' : '#9898b0', animation: mode === 'pending' ? 'pulse 1.5s infinite' : 'none' }}>
            {mode === 'pending' ? '…' : mode.toUpperCase()}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.5, fontSize: '16px', color: '#9898b0' }}>
            ⚡ Ask JARVIS anything…
          </div>
        ) : messages.map((msg) => (
          <div key={msg.id} style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            padding: '12px 16px',
            borderRadius: '12px',
            fontSize: '20px',
            lineHeight: 1.5,
            background: msg.role === 'user' ? 'linear-gradient(135deg, #3b82f6, #2563eb)' : msg.role === 'error' ? 'rgba(239,68,68,0.12)' : 'rgba(22,22,35,0.9)',
            color: msg.role === 'error' ? '#f59e0b' : '#e8e8f0',
            border: msg.role === 'user' ? 'none' : '1px solid rgba(100,140,255,0.1)',
          }}>
            {msg.text}{msg.streaming ? '▊' : ''}
          </div>
        ))}
        {isStreaming && messages[messages.length - 1]?.text === '' && (
          <div style={{ alignSelf: 'flex-start', padding: '14px 18px', background: 'rgba(22,22,35,0.9)', borderRadius: '12px', border: '1px solid rgba(100,140,255,0.1)' }}>
            <span style={{ opacity: 0.6 }}>Thinking…</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(100,140,255,0.1)' }}>
        <form onSubmit={(e) => { e.preventDefault(); const input = inputRef.current; if (input?.value) { handleSend(input.value); input.value = ''; } }} style={{ display: 'flex', gap: '8px', background: 'rgba(30,30,48,0.85)', borderRadius: '12px', padding: '4px 4px 4px 16px', border: '1px solid rgba(100,140,255,0.1)' }}>
          <input ref={inputRef} type="text" placeholder={isStreaming ? 'JARVIS is thinking…' : 'Ask JARVIS anything…'} disabled={isStreaming} autoFocus style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#e8e8f0', fontSize: '16px', fontFamily: 'inherit', padding: '10px 0' }} />
          <button type="submit" disabled={isStreaming} style={{ width: 40, height: 40, borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #00d4ff, #3b82f6)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>↑</button>
        </form>
      </div>

      {/* Surface card */}
      {surfaceData && (
        <div style={{ position: 'absolute', bottom: '100%', right: 0, width: 320, marginBottom: 8, background: 'rgba(12,12,20,0.95)', border: '1px solid rgba(100,140,255,0.25)', borderRadius: 12, padding: 16, boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#00d4ff', letterSpacing: 1, textTransform: 'uppercase' }}>Context</span>
            <button onClick={handleDismissSurface} style={{ background: 'transparent', border: '1px solid rgba(100,140,255,0.1)', borderRadius: 6, color: '#9898b0', cursor: 'pointer', width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>×</button>
          </div>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {surfaceData.bullets.map((b, i) => (
              <li key={i} style={{ fontSize: 14, color: '#e8e8f0', paddingLeft: 16, position: 'relative', lineHeight: 1.6 }}>
                <span style={{ position: 'absolute', left: 0, color: '#00d4ff' }}>▸</span>{b}
              </li>
            ))}
          </ul>
          <span style={{ display: 'inline-block', marginTop: 8, padding: '3px 10px', background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', borderRadius: 20, fontSize: 12, color: '#00d4ff', fontFamily: 'Consolas, monospace' }}>{surfaceData.file}</span>
        </div>
      )}
    </div>
  );
}
