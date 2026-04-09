import { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import useWebSocket from './hooks/useWebSocket';


// ─── Message reducer ─────────────────────────────────────
function messageReducer(state, action) {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return [...state, { id: Date.now(), role: 'user', text: action.text, timestamp: new Date() }];
    case 'ADD_JARVIS_MESSAGE':
      return [...state, { id: Date.now(), role: 'jarvis', text: action.text, timestamp: new Date() }];
    case 'START_STREAM':
      return [...state, { id: action.id || Date.now(), role: 'jarvis', text: '', timestamp: new Date(), streaming: true }];
    case 'APPEND_CHUNK':
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, text: msg.text + action.text } : msg);
    case 'FINISH_STREAM':
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, streaming: false } : msg);
    case 'REPLACE_RESPONSE':
      return state.map((msg, i) => i === state.length - 1 && msg.role === 'jarvis' ? { ...msg, text: action.text, streaming: false } : msg);
    case 'ADD_ERROR':
      return [...state, { id: Date.now(), role: 'error', text: action.message, timestamp: new Date() }];
    case 'CLEAR':
      return [];
    default:
      return state;
  }
}

// ─── SVG Icons ────────────────────────────────────────────

const IconFilter = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="4" y1="6" x2="20" y2="6"/>
    <line x1="8" y1="12" x2="16" y2="12"/>
    <line x1="11" y1="18" x2="13" y2="18"/>
  </svg>
);

const IconMore = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
    <circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/>
  </svg>
);


const IconGrid = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
  </svg>
);

const IconSidebarRight = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="18" height="18" rx="2"/>
    <line x1="15" y1="3" x2="15" y2="21"/>
  </svg>
);

const IconSend = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
);

const IconPlus = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);

// ─── Mode Toggle (single pill: Secure ↔ Cloud) ───────────
function ModeToggle({ mode, onToggle }) {
  const isCloud = mode === 'cloud';
  const isPending = mode === 'pending';
  return (
    <div
      className={`mode-pill${isPending ? ' disabled' : ''}`}
      onClick={isPending ? undefined : onToggle}
      title={isCloud ? 'Switch to Secure Mode' : 'Switch to Cloud Mode'}
    >
      <span className={`mode-label${!isCloud && !isPending ? ' active-secure' : ''}`}>Secure</span>
      <div className={`mode-track${isCloud ? ' cloud' : isPending ? ' pending' : ' secure'}`}>
        <div className="mode-dot" />
      </div>
      <span className={`mode-label${isCloud ? ' active-cloud' : ''}`}>Cloud</span>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────
export default function App() {
  const [messages, dispatch] = useReducer(messageReducer, []);
  const [isStreaming, setIsStreaming] = useState(false);
  const isStreamingRef = useRef(false); // sync ref — avoids stale closure in WS handlers
  const [mode, setMode] = useState('local');
  const [surfaceData, setSurfaceData] = useState(null);
  const [showStartup, setShowStartup] = useState(true);
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);

  const { sendMessage, connectionStatus } = useWebSocket('ws://localhost:8765', {
    onStreamChunk: (event) => {
      if (!isStreamingRef.current) {
        isStreamingRef.current = true;
        setIsStreaming(true);
        dispatch({ type: 'START_STREAM' });
      }
      dispatch({ type: 'APPEND_CHUNK', text: event.text });
      if (event.done) { isStreamingRef.current = false; dispatch({ type: 'FINISH_STREAM' }); setIsStreaming(false); }
    },
    onResponse: (event) => {
      if (isStreamingRef.current) {
        isStreamingRef.current = false;
        dispatch({ type: 'REPLACE_RESPONSE', text: event.text });
        setIsStreaming(false);
      } else {
        dispatch({ type: 'ADD_JARVIS_MESSAGE', text: event.text });
      }
    },
    onSurface: (event) => { setSurfaceData({ bullets: event.bullets, file: event.file }); },
    onModeAck: (event) => { setMode(event.mode); },
    onError: (event) => { dispatch({ type: 'ADD_ERROR', message: event.message }); setIsStreaming(false); },
  });

  useEffect(() => {
    if (window.jarvis?.onToggleOverlay) {
      return window.jarvis.onToggleOverlay(() => setTimeout(() => inputRef.current?.focus(), 50));
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback((text) => {
    if (!text.trim() || isStreaming) return;
    dispatch({ type: 'ADD_USER_MESSAGE', text: text.trim() });
    sendMessage({ type: 'user_query', text: text.trim(), mode });
  }, [isStreaming, mode, sendMessage]);

  const handleModeToggle = useCallback(() => {
    const next = mode === 'cloud' ? 'local' : 'cloud';
    setMode(next);
    sendMessage({ type: 'mode_change', mode: next });
  }, [mode, sendMessage]);

  const handleDismissSurface = useCallback(() => {
    if (surfaceData) {
      sendMessage({ type: 'surface_dismissed', file: surfaceData.file });
      setSurfaceData(null);
    }
  }, [surfaceData, sendMessage]);

  useEffect(() => {
    if (!surfaceData) return;
    const timer = setTimeout(handleDismissSurface, 8000);
    return () => clearTimeout(timer);
  }, [surfaceData, handleDismissSurface]);

  // ─── Splash Screen ───────────────────────────────────────
  if (showStartup) {
    return (
      <div className="splash-screen" style={{ WebkitAppRegion: 'drag' }}>
        <div className="splash-system-badge">
          <div className="splash-line" />
          SYSTEM ONLINE
          <div className="splash-line" />
        </div>

        <h1 className="splash-title">J.A.R.V.I.S</h1>

        <p className="splash-subtitle">JUST A RATHER VERY INTELLIGENT SYSTEM</p>

        <button
          className="splash-btn"
          onClick={() => setShowStartup(false)}
          style={{ WebkitAppRegion: 'no-drag' }}
        >
          START YOUR CONVO
        </button>

        <div className="splash-status" style={{ WebkitAppRegion: 'no-drag' }}>
          <div className={`splash-dot ${connectionStatus === 'connected' ? 'ready' : 'connecting'}`} />
          {connectionStatus === 'connected' ? 'READY' : 'CONNECTING...'}
        </div>
      </div>
    );
  }

  // ─── Main Layout ─────────────────────────────────────────
  return (
    <div className="app-container">

      {/* Proactive Surface Card */}
      {surfaceData && (
        <div className="surface-card">
          <div className="surface-header">
            <span className="surface-file">{surfaceData.file}</span>
            <button className="surface-dismiss" onClick={handleDismissSurface}>✕</button>
          </div>
          {surfaceData.bullets.map((bullet, i) => (
            <p key={i} className="surface-bullet">• {bullet}</p>
          ))}
        </div>
      )}

      {/* ══ Left Sidebar ══ */}
      <div className="sidebar sidebar-left">
        {/* Sidebar header — draggable */}
        <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0, overflow: 'hidden' }}>
            <div className="workspace-avatar">J</div>
            <span className="workspace-title">Untitled workspace</span>
          </div>
          <div style={{ display: 'flex', gap: 2, WebkitAppRegion: 'no-drag', flexShrink: 0 }}>
            <button className="icon-btn" onClick={() => setShowStartup(true)} title="Home">←</button>
            <button className="icon-btn" title="Grid view"><IconGrid /></button>
            <button className="icon-btn new-session-btn" title="New session">+ New session</button>
          </div>
        </div>

        {/* Sidebar body */}
        <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag' }}>
          <div style={{ padding: '12px 14px 0' }}>
            <div className="section-label">Previous Conversations</div>

            <div className="conv-list">
              <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
                No conversations yet.
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar footer */}
        <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag' }}>
          <div className="user-avatar" title="Profile">N</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className={`conn-dot ${mode === 'cloud' ? 'connected' : 'offline'}`} />
            <span className="conn-label">
              {mode === 'cloud' ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </div>

      {/* ══ Main Chat Area ══ */}
      <div className="chat-area">

        {/* Chat header — draggable */}
        <div className="chat-header" style={{ WebkitAppRegion: 'drag' }}>
          <span className="chat-title">Chat</span>

          {/* Mode toggle */}
          <div className="header-toggles" style={{ WebkitAppRegion: 'no-drag' }}>
            <ModeToggle mode={mode} onToggle={handleModeToggle} />
          </div>

          {/* Header action icons */}
          <div style={{ display: 'flex', gap: 2, WebkitAppRegion: 'no-drag' }}>
            <button className="icon-btn" title="Filter conversations"><IconFilter /></button>
            <button className="icon-btn" title="More options"><IconMore /></button>
          </div>
        </div>

        {/* Messages */}
        <div className="messages-area">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-avatar">J</div>
              <h2 className="empty-title">How can I help you today?</h2>
              <p className="empty-subtitle">Ask questions, generate code, or analyze your workspace.</p>
            </div>
          ) : (
            <div className="messages-list">
              {messages.map((msg) => (
                <div key={msg.id} className={`message-row ${msg.role}`}>
                  <div className={`message-bubble ${msg.role}`}>
                    {msg.text}
                    {msg.streaming && <span className="streaming-cursor">▊</span>}
                  </div>
                </div>
              ))}
              {isStreaming && messages[messages.length - 1]?.text === '' && (
                <div className="thinking-indicator">JARVIS is thinking…</div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="input-area" style={{ WebkitAppRegion: 'no-drag' }}>
          <div className="chat-input-wrapper">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const val = inputRef.current?.value?.trim();
                if (val) { handleSend(val); inputRef.current.value = ''; }
              }}
            >
              <input
                ref={inputRef}
                type="text"
                placeholder="Message JARVIS..."
                disabled={isStreaming}
                className="chat-input"
              />
            </form>
            <div className="input-footer">
              <span className="input-disclaimer">JARVIS can be inaccurate, please double check its responses.</span>
              <button
                className="btn-send"
                disabled={isStreaming}
                onClick={() => {
                  const val = inputRef.current?.value?.trim();
                  if (val) { handleSend(val); inputRef.current.value = ''; }
                }}
                title="Send"
              >
                <IconSend />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ══ Right Sidebar ══ */}
      <div className="sidebar sidebar-right">
        <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
          <span className="chat-title">Reports</span>
          <button className="icon-btn" style={{ WebkitAppRegion: 'no-drag' }} title="Collapse sidebar">
            <IconSidebarRight />
          </button>
        </div>

        <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag', padding: '16px 14px' }}>
          <div className="section-label" style={{ marginBottom: 14 }}>Generated Reports</div>

          <div className="reports-list">
            <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
              No reports generated yet.
            </div>
          </div>
        </div>

        <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag', justifyContent: 'flex-end' }}>
          <button className="btn-add-note">
            <IconPlus /> Add note
          </button>
        </div>
      </div>

    </div>
  );
}
