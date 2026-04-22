/**
 * AutoResearchProgress — progress card for the §6 auto-research loop.
 * Renders nothing until a progress event arrives; hides itself when the
 * loop signals `phase: "done"` (parent nulls the prop).
 */
export default function AutoResearchProgress({ progress }) {
  if (!progress) return null;
  const { iteration, total, currentScore, bestScore, spentUsd, phase } = progress;
  const pct = total ? Math.round((iteration / total) * 100) : 0;
  return (
    <div className="auto-research-card" role="status" aria-live="polite">
      <div className="auto-research-header">
        <span className="auto-research-title">Auto-research</span>
        <span className="auto-research-phase">{phase}</span>
      </div>
      <div className="auto-research-bar">
        <div className="auto-research-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="auto-research-meta">
        <span>Iter {iteration}/{total}</span>
        {currentScore != null && <span>score {currentScore.toFixed(2)}</span>}
        {bestScore != null && <span>best {bestScore.toFixed(2)}</span>}
        {spentUsd != null && <span>${spentUsd.toFixed(2)}</span>}
      </div>
    </div>
  );
}
