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
      <SidebarLeft mode={mode} onGoHome={() => setShowStartup(true)} />
      <ChatArea
        messages={messages}
        isStreaming={isStreaming}
        mode={mode}
        inputRef={inputRef}
        messagesEndRef={messagesEndRef}
        onSend={handleSend}
        onModeToggle={handleModeToggle}
      />
      <SidebarRight />
    </div>
  );
}
