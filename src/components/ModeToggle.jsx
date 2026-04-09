export default function ModeToggle({ mode, onToggle }) {
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
