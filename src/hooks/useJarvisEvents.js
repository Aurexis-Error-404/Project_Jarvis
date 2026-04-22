import { TOOL_DONE_REMOVE_MS } from '../constants/config';

/**
 * useJarvisEvents — wires all backend WebSocket events to state dispatchers.
 * Extracted from App.jsx to keep App lean and event logic testable.
 */
export default function buildJarvisEventHandlers({
  dispatch,
  isStreamingRef,
  discardStreamRef,
  setIsStreaming,
  setSurfaceData,
  setMode,
  setReports,
  setReportReady,
  setActiveTools,
  setProjectPath,
  setOrchestratorStatus,
  setAutoResearchProgress,
  setConsentRequest,
}) {
  return {
    onStreamChunk: (event) => {
      if (discardStreamRef.current) return;
      if (!isStreamingRef.current) {
        isStreamingRef.current = true;
        setIsStreaming(true);
        dispatch({ type: 'START_STREAM' });
      }
      if (event.text) dispatch({ type: 'APPEND_CHUNK', text: event.text });
      if (event.done) {
        isStreamingRef.current = false;
        dispatch({ type: 'FINISH_STREAM' });
        setIsStreaming(false);
      }
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

    onSurface: (event) => {
      setSurfaceData({ bullets: event.bullets, file: event.file });
    },

    onModeAck: (event) => { setMode(event.mode); },

    onError: (event) => {
      if (isStreamingRef.current) dispatch({ type: 'FINISH_STREAM' });
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

    onStatusUpdate: () => { /* transient — no state update needed */ },

    onProjectPathAck: (event) => { setProjectPath(event.path); },

    onOrchestratorStatus: (event) => {
      if (typeof setOrchestratorStatus === 'function') {
        setOrchestratorStatus({
          strategy: event.strategy,
          phase: event.phase,
          iteration: event.iteration,
          total: event.total,
        });
      }
    },

    onAutoResearchProgress: (event) => {
      if (typeof setAutoResearchProgress !== 'function') return;
      if (event.phase === 'done') {
        setAutoResearchProgress(null);
        return;
      }
      setAutoResearchProgress({
        iteration: event.iteration,
        total: event.total,
        currentScore: event.current_score,
        bestScore: event.best_score,
        spentUsd: event.spent_usd,
        phase: event.phase,
      });
    },

    onConsentRequest: (event) => {
      if (typeof setConsentRequest === 'function') {
        setConsentRequest({
          requestId: event.request_id,
          action: event.action,
          payload: event.payload || {},
          timeoutS: event.timeout_s,
        });
      }
    },

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
        }, TOOL_DONE_REMOVE_MS);
      }
    },
  };
}
