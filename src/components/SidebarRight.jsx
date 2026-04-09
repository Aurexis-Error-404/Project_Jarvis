import { IconSidebarRight } from './Icons';

export default function SidebarRight({ reports = [] }) {
  const handleOpenReport = async (path) => {
    try {
      await window.jarvis?.openLocalFile(path);
    } catch (e) {
      console.warn('[JARVIS] Could not open report:', e.message);
    }
  };

  return (
    <div className="sidebar sidebar-right">
      <div className="sidebar-header" style={{ WebkitAppRegion: 'drag' }}>
        <span className="chat-title">Reports</span>
        <span style={{ fontSize: 10, color: '#52525b', WebkitAppRegion: 'no-drag' }}>
          {reports.length > 0 ? `${reports.length} generated` : ''}
        </span>
      </div>

      <div className="sidebar-body" style={{ WebkitAppRegion: 'no-drag', padding: '16px 14px' }}>
        <div className="section-label" style={{ marginBottom: 14 }}>Generated Reports</div>
        <div className="reports-list">
          {reports.length === 0 ? (
            <div style={{ color: '#555', fontSize: 11, padding: '8px 0', fontFamily: 'monospace' }}>
              Ask JARVIS to generate a report.
            </div>
          ) : (
            reports.map((report, i) => (
              <div
                key={i}
                className="report-item"
                onClick={() => handleOpenReport(report.path)}
              >
                <div className="report-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                </div>
                <div className="report-info">
                  <div className="report-title">{report.name}</div>
                  <div className="report-meta">{report.time}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
