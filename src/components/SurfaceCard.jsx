import { useEffect, useRef, useCallback } from 'react';
import { SURFACE_DISMISS_MS } from '../constants/config';

export default function SurfaceCard({ surfaceData, onDismiss }) {
  const dismissTimerRef = useRef(null);
  const signalLabel = surfaceData.signalType === 'wiki_note' ? 'Wiki Context' : 'Code Context';

  const startDismissTimer = useCallback(() => {
    dismissTimerRef.current = setTimeout(onDismiss, SURFACE_DISMISS_MS);
  }, [onDismiss]);

  const clearDismissTimer = useCallback(() => {
    clearTimeout(dismissTimerRef.current);
  }, []);

  useEffect(() => {
    startDismissTimer();
    return clearDismissTimer;
  }, [startDismissTimer, clearDismissTimer]);

  return (
    <div className="surface-card" onMouseEnter={clearDismissTimer} onMouseLeave={startDismissTimer}>
      <div className="surface-header">
        <div>
          <div className="surface-file">{surfaceData.file}</div>
          <div className="surface-kind">{signalLabel}</div>
        </div>
        <button className="surface-dismiss" onClick={onDismiss}>✕</button>
      </div>
      {surfaceData.bullets.map((bullet, i) => (
        <p key={i} className="surface-bullet">• {bullet}</p>
      ))}
    </div>
  );
}
