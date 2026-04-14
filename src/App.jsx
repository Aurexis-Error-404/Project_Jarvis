import { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import { WS_URL, SPLASH_DISMISS_MS, INPUT_FOCUS_MS } from './constants/config';
import useWebSocket from './hooks/useWebSocket';
import useConversations from './hooks/useConversations';
import buildJarvisEventHandlers from './hooks/useJarvisEvents';
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
  const discardStreamRef = useRef(false);
  const manualSplashRef = useRef(false);
  const [mode, setMode] = useState('local');
  const [surfaceData, setSurfaceData] = useState(null);
  const [reportReady, setReportReady] = useState(null);
  const [reports, setReports] = useState(() => {
    try { return JSON.parse(localStorage.getItem('jarvis_reports') || '[]'); }
    catch { return []; }
  });
<<<<<<< HEAD
=======
  const [conversations, setConversations] = useState(() => {
    try { return JSON.parse(localStorage.getItem('jarvis_conversations') || '[]'); }
    catch { return []; }
  });
  const [activeConvId, setActiveConvId] = useState(null);
>>>>>>> e389db3f56978f7d7f15cde282a77e0feef7c135
  const [showStartup, setShowStartup] = useState(true);
  const [activeTools, setActiveTools] = useState([]);
  const [projectPath, setProjectPath] = useState(null);
  const inputRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Persist reports across restarts
  useEffect(() => {
    localStorage.setItem('jarvis_reports', JSON.stringify(reports));
  }, [reports]);

<<<<<<< HEAD
  const { conversations, activeConvId, autoTitle, syncMessages, selectConv, newSession } = useConversations({
    dispatch, discardStreamRef, isStreamingRef, setIsStreaming, setActiveTools,
=======
  // Persist conversations across restarts
  useEffect(() => {
    localStorage.setItem('jarvis_conversations', JSON.stringify(conversations));
  }, [conversations]);

  // Save messages into the active conversation on every change
  useEffect(() => {
    if (activeConvId && messages.length > 0) {
      setConversations(prev => prev.map(c =>
        c.id === activeConvId ? { ...c, messages } : c
      ));
    }
  }, [messages, activeConvId]);

  const { sendMessage, connectionStatus } = useWebSocket('ws://localhost:8765', {
    onStreamChunk: (event) => {
      if (discardStreamRef.current) return;
      if (!isStreamingRef.current) {
        isStreamingRef.current = true;
        setIsStreaming(true);
        dispatch({ type: 'START_STREAM' });
      }
      if (event.text) {
        dispatch({ type: 'APPEND_CHUNK', text: event.text });
      }
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
    onError: (event) => {
      if (isStreamingRef.current) { dispatch({ type: 'FINISH_STREAM' }); }
      dispatch({ type: 'ADD_ERROR', message: event.message });
      isStreamingRef.current = false;
      setIsStreaming(false);
      setActiveTools([]);
    },
    onReportGenerated: (event) => {
      setReportReady({ path: event.path });
      const name = event.path.split(/[\\/]/).pop() || 'Report';
      setReports(prev => [{ path: event.path, name, time: new Date().toLocaleTimeString() }, ...prev]);
    },
    onStatusUpdate: () => { /* transient */ },
    onProjectPathAck: (event) => { setProjectPath(event.path); },
    onToolCallStatus: (event) => {
      if (event.status === 'start') {
        setActiveTools(prev => [...prev, {
          tool: event.tool, params: event.params || {}, status: 'running',
        }]);
      } else {
        setActiveTools(prev => prev.map(t =>
          t.tool === event.tool && t.status === 'running'
            ? { ...t, status: 'done', duration: event.duration_ms }
            : t
        ));
        setTimeout(() => {
          setActiveTools(prev => prev.filter(t =>
            !(t.tool === event.tool && t.status === 'done')
          ));
        }, 1500);
      }
    },
>>>>>>> e389db3f56978f7d7f15cde282a77e0feef7c135
  });

  // Sync messages into active conversation on every change
  useEffect(() => { syncMessages(messages); }, [messages, syncMessages]);

  const { sendMessage, connectionStatus } = useWebSocket(
    WS_URL,
    buildJarvisEventHandlers({
      dispatch, isStreamingRef, discardStreamRef,
      setIsStreaming, setSurfaceData, setMode,
      setReports, setReportReady, setActiveTools, setProjectPath,
    })
  );

  useEffect(() => {
    if (window.jarvis?.onToggleOverlay) {
      return window.jarvis.onToggleOverlay(() => setTimeout(() => inputRef.current?.focus(), INPUT_FOCUS_MS));
    }
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') { manualSplashRef.current = true; setShowStartup(true); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-skip splash on connect — only on cold start, not manual returns
  useEffect(() => {
    if (showStartup && connectionStatus === 'connected' && !manualSplashRef.current) {
      const t = setTimeout(() => setShowStartup(false), SPLASH_DISMISS_MS);
      return () => clearTimeout(t);
    }
  }, [showStartup, connectionStatus]);

  useEffect(() => {
    if (connectionStatus === 'disconnected' && isStreamingRef.current) {
      isStreamingRef.current = false;
      setIsStreaming(false);
    }
  }, [connectionStatus]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback((text) => {
    discardStreamRef.current = false;
    if (!text.trim() || isStreaming) return;
    dispatch({ type: 'ADD_USER_MESSAGE', text: text.trim() });
    dispatch({ type: 'START_STREAM' });
    isStreamingRef.current = true;
    setIsStreaming(true);
    sendMessage({ event: 'user_query', query: text.trim(), mode });
    autoTitle(text.trim(), messages.length);
  }, [isStreaming, mode, sendMessage, messages.length, autoTitle]);

  const handleModeToggle = useCallback(() => {
    const next = mode === 'cloud' ? 'local' : 'cloud';
    setMode('pending');
    sendMessage({ event: 'mode_change', mode: next });
  }, [mode, sendMessage]);

  const handleNewSession = useCallback(() => {
    newSession(() => { setReportReady(null); setSurfaceData(null); });
    setTimeout(() => inputRef.current?.focus(), INPUT_FOCUS_MS);
  }, [newSession]);

  const handleSelectProject = useCallback(async () => {
    const dir = await window.jarvis?.selectProjectDir();
    if (dir) sendMessage({ event: 'set_project_path', path: dir });
  }, [sendMessage]);

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
        onStart={() => { manualSplashRef.current = false; setShowStartup(false); }}
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
                setReportReady(prev => ({ ...prev, error: `Could not open — ${prev.path}` }));
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
        onGoHome={() => { manualSplashRef.current = true; setShowStartup(true); }}
        onNewSession={handleNewSession}
        conversations={conversations}
        activeConvId={activeConvId}
        onSelectConv={selectConv}
        projectPath={projectPath}
        onSelectProject={handleSelectProject}
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
        connectionStatus={connectionStatus}
      />
      <SidebarRight reports={reports} />
    </div>
  );
}
