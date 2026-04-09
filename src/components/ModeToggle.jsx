export default function ModeToggle({ mode, onToggle }) {
  const isCloud = mode === 'cloud';
  return (
    <div
      className="mode-pill"
      onClick={onToggle}
      title={isCloud ? 'Switch to Secure Mode' : 'Switch to Cloud Mode'}
    >
      <span className={`mode-label${!isCloud ? ' active-secure' : ''}`}>Secure</span>
      <div className={`mode-track${isCloud ? ' cloud' : ' secure'}`}>
        <div className="mode-dot" />
      </div>
      <span className={`mode-label${isCloud ? ' active-cloud' : ''}`}>Cloud</span>
    </div>
  );
}
