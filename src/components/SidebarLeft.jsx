import { IconGrid } from './Icons';

export default function SidebarLeft({ connectionStatus, onGoHome }) {
  return (
    <div className="sidebar sidebar-left">
      <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0, overflow: 'hidden' }}>
          <div className="workspace-avatar">J</div>
          <span className="workspace-title">Untitled workspace</span>
        </div>
        <div style={{ display: 'flex', gap: 2, WebkitAppRegion: 'no-drag', flexShrink: 0 }}>
          <button className="icon-btn" onClick={onGoHome} title="Home">←</button>
          <button className="icon-btn" title="Grid view"><IconGrid /></button>
          <button className="icon-btn new-session-btn" title="New session">+ New session</button>
        </div>
      </div>

      <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag' }}>
        <div style={{ padding: '12px 14px 0' }}>
          <div className="section-label">Previous Conversations</div>
          <div className="conv-list">
            <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
              No conversations yet.
            </div>
          </div>
        </div>
      </div>

      <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag' }}>
        <div className="user-avatar" title="Profile">N</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div className={`conn-dot ${connectionStatus === 'connected' ? 'connected' : 'offline'}`} />
          <span className="conn-label">
            {connectionStatus === 'connected' ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>
    </div>
  );
}
