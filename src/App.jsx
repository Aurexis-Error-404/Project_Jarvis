import { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import useWebSocket from './hooks/useWebSocket';
import messageReducer from './reducers/messageReducer';
import SplashScreen from './components/SplashScreen';
import SurfaceCard from './components/SurfaceCard';
import SidebarLeft from './components/SidebarLeft';
import SidebarRight from './components/SidebarRight';
import ChatArea from './components/ChatArea';

export default function App() {
  const [messages, dispatch] = useReducer(messageReducer, []);
  const [isStreaming, setIsStreaming] = useState(false);
  const isStreamingRef = useRef(false);
  const [mode, setMode] = useState('local');
  const [surfaceData, setSurfaceData] = useState(null);
  const [reportReady, setReportReady] = useState(null); // { path }
  const [reports, setReports] = useState([]); // list of generated reports
  const [conversations, setConversations] = useState([]); // conversation history
  const [activeConvId, setActiveConvId] = useState(null);
  const [showStartup, setShowStartup] = useState(true);
  const [activeTools, setActiveTools] = useState([]); // tools currently running
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
    onError: (event) => { dispatch({ type: 'ADD_ERROR', message: event.message }); setIsStreaming(false); setActiveTools([]); },
    onReportGenerated: (event) => {
      setReportReady({ path: event.path });
      // Add to reports list for sidebar
      const name = event.path.split(/[\\/]/).pop() || 'Report';
      setReports(prev => [{ path: event.path, name, time: new Date().toLocaleTimeString() }, ...prev]);
    },
    onStatusUpdate: () => { /* transient — backend signals thinking start */ },
    onToolCallStatus: (event) => {
      if (event.status === 'start') {
        setActiveTools(prev => [...prev, event.tool]);
      } else {
        setActiveTools(prev => prev.filter(t => t !== event.tool));
      }
    },
  });

  useEffect(() => {
    if (window.jarvis?.onToggleOverlay) {
      return window.jarvis.onToggleOverlay(() => setTimeout(() => inputRef.current?.focus(), 50));
    }
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setShowStartup(true);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback((text) => {
    if (!text.trim() || isStreaming) return;
    dispatch({ type: 'ADD_USER_MESSAGE', text: text.trim() });
    sendMessage({ event: 'user_query', query: text.trim(), mode });
    // Auto-title the first message of a new conversation
    if (messages.length === 0 && !activeConvId) {
      const id = Date.now().toString();
      const title = text.trim().slice(0, 40) + (text.trim().length > 40 ? '...' : '');
      setActiveConvId(id);
      setConversations(prev => [{ id, title, time: new Date().toLocaleTimeString() }, ...prev]);
    }
  }, [isStreaming, mode, sendMessage, messages.length, activeConvId]);

  const handleModeToggle = useCallback(() => {
    const next = mode === 'cloud' ? 'local' : 'cloud';
    setMode(next);
    sendMessage({ event: 'mode_change', mode: next });
  }, [mode, sendMessage]);

  const handleNewSession = useCallback(() => {
    dispatch({ type: 'CLEAR' });
    setActiveConvId(null);
    setActiveTools([]);
    setIsStreaming(false);
    isStreamingRef.current = false;
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const handleDismissSurface = useCallback(() => {
    if (surfaceData) {
      sendMessage({ event: 'surface_dismissed', file: surfaceData.file });
      setSurfaceData(null);
    }
  }, [surfaceData, sendMessage]);

  if (showStartup) {
    return (
      <SplashScreen
        connectionStatus={connectionStatus}
        onStart={() => setShowStartup(false)}
      />
    );
  }

  return (
    <div className="app-container">
      {surfaceData && (
        <SurfaceCard surfaceData={surfaceData} onDismiss={handleDismissSurface} />
      )}

      {reportReady && (
        <div className="report-toast">
          <span>{reportReady.error ?? 'Report ready.'}</span>
          <button
            onClick={async () => {
              try {
                await window.jarvis?.openLocalFile(reportReady.path);
                setReportReady(null);
              } catch (e) {
                setReportReady(prev => ({ ...prev, error: `Could not open — ${reportReady.path}` }));
              }
            }}
          >
            Open Report
          </button>
          <button className="surface-dismiss" onClick={() => setReportReady(null)}>✕</button>
        </div>
      )}
      <SidebarLeft
        connectionStatus={connectionStatus}
        onGoHome={() => setShowStartup(true)}
        onNewSession={handleNewSession}
        conversations={conversations}
        activeConvId={activeConvId}
      />
      <ChatArea
        messages={messages}
        isStreaming={isStreaming}
        mode={mode}
        inputRef={inputRef}
        messagesEndRef={messagesEndRef}
        onSend={handleSend}
        onModeToggle={handleModeToggle}
        activeTools={activeTools}
      />
      <SidebarRight reports={reports} />
    </div>
  );
}
