import { useEffect, useRef, useCallback } from 'react';

export default function SurfaceCard({ surfaceData, onDismiss }) {
  const dismissTimerRef = useRef(null);

  const startDismissTimer = useCallback(() => {
    dismissTimerRef.current = setTimeout(onDismiss, 8000);
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
        <span className="surface-file">{surfaceData.file}</span>
        <button className="surface-dismiss" onClick={onDismiss}>✕</button>
      </div>
      {surfaceData.bullets.map((bullet, i) => (
        <p key={i} className="surface-bullet">• {bullet}</p>
      ))}
    </div>
  );
}
