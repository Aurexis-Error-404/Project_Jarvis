import ModeToggle from './ModeToggle';
import { IconSend } from './Icons';
import renderMarkdown from '../utils/renderMarkdown';

const TOOL_LABELS = {
  read_codebase: 'Reading codebase',
  read_git_history: 'Checking git history',
  web_research: 'Searching the web',
  generate_html_report: 'Generating report',
  update_project_memory: 'Updating memory',
  read_session_history: 'Loading session history',
};

export default function ChatArea({ messages, isStreaming, mode, inputRef, messagesEndRef, onSend, onModeToggle, activeTools = [] }) {
  return (
    <div className="chat-area">
      <div className="chat-header" style={{ WebkitAppRegion: 'drag' }}>
        <span className="chat-title">Chat</span>
        <div className="header-toggles" style={{ WebkitAppRegion: 'no-drag' }}>
          <ModeToggle mode={mode} onToggle={onModeToggle} />
        </div>
      </div>

      <div className="messages-area">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-avatar">J</div>
            <h2 className="empty-title">How can I help you today?</h2>
            <p className="empty-subtitle">Ask questions, generate code, or analyze your workspace.</p>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((msg) => (
              <div key={msg.id} className={`message-row ${msg.role}`}>
                <div className={`message-bubble ${msg.role}`}>
                  {msg.role === 'jarvis' ? (
                    <div className="markdown-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.text) }} />
                  ) : (
                    msg.text
                  )}
                  {msg.streaming && <span className="streaming-cursor">▊</span>}
                </div>
              </div>
            ))}
            {/* Tool progress indicators */}
            {activeTools.length > 0 && (
              <div className="tool-progress">
                {activeTools.map((t, i) => (
                  <div key={i} className={`tool-progress-item ${t.status || 'running'}`}>
                    <div className={`tool-progress-dot ${t.status || 'running'}`} />
                    <span className="tool-name">{TOOL_LABELS[t.tool] || t.tool}...</span>
                    {t.params && Object.keys(t.params).length > 0 && (
                      <span className="tool-params">
                        {Object.entries(t.params).map(([k, v]) => `${k}: ${v}`).join(', ')}
                      </span>
                    )}
                    {t.status === 'done' && t.duration != null && (
                      <span className="tool-duration">{t.duration}ms</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {isStreaming && messages[messages.length - 1]?.text === '' && activeTools.length === 0 && (
              <div className="thinking-indicator">JARVIS is thinking…</div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="input-area" style={{ WebkitAppRegion: 'no-drag' }}>
        <div className="chat-input-wrapper">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const val = inputRef.current?.value?.trim();
              if (val) { onSend(val); inputRef.current.value = ''; }
            }}
          >
            <input
              ref={inputRef}
              type="text"
              placeholder={mode === 'local' ? 'Message JARVIS (Secure Mode)...' : 'Message JARVIS...'}
              disabled={isStreaming}
              className="chat-input"
            />
          </form>
          <div className="input-footer">
            <span className="input-disclaimer">
              {mode === 'local' ? '🔒 Secure mode — all data stays local' : 'JARVIS can be inaccurate, please double check its responses.'}
            </span>
            <button
              className="btn-send"
              disabled={isStreaming}
              onClick={() => {
                const val = inputRef.current?.value?.trim();
                if (val) { onSend(val); inputRef.current.value = ''; }
              }}
              title="Send"
            >
              <IconSend />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
