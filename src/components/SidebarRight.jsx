import { IconSidebarRight, IconPlus } from './Icons';

export default function SidebarRight() {
  return (
    <div className="sidebar sidebar-right">
      <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
        <span className="chat-title">Reports</span>
        <button className="icon-btn" style={{ WebkitAppRegion: 'no-drag' }} title="Collapse sidebar" disabled>
          <IconSidebarRight />
        </button>
      </div>

      <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag', padding: '16px 14px' }}>
        <div className="section-label" style={{ marginBottom: 14 }}>Generated Reports</div>
        <div className="reports-list">
          <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
            No reports generated yet.
          </div>
        </div>
      </div>

      <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag', justifyContent: 'flex-end' }}>
        <button className="btn-add-note" disabled title="TODO: implement notes">
          <IconPlus /> Add note
        </button>
      </div>
    </div>
  );
}
