import { IconGrid } from './Icons';

export default function SidebarLeft({ connectionStatus, onGoHome, onNewSession, conversations = [], activeConvId }) {
  return (
    <div className="sidebar sidebar-left">
      <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0, overflow: 'hidden' }}>
          <div className="workspace-avatar">J</div>
          <span className="workspace-title">JARVIS Workspace</span>
        </div>
        <div style={{ display: 'flex', gap: 2, WebkitAppRegion: 'no-drag', flexShrink: 0 }}>
          <button className="icon-btn" onClick={onGoHome} title="Home">←</button>
          <button className="icon-btn new-session-btn" onClick={onNewSession} title="New session">+ New session</button>
        </div>
      </div>

      <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag' }}>
        <div style={{ padding: '12px 14px 0' }}>
          <div className="section-label">Conversations</div>
          <div className="conv-list">
            {conversations.length === 0 ? (
              <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
                Start a conversation to see history.
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`conversation-item${conv.id === activeConvId ? ' active' : ''}`}
                >
                  <div className="conversation-title">{conv.title}</div>
                  <div className="conversation-time">{conv.time}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag' }}>
        <div className="user-avatar" title="Profile">J</div>
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
