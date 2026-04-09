export default function SplashScreen({ connectionStatus, onStart }) {
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
        onClick={onStart}
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
