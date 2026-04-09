import ModeToggle from './ModeToggle';
import { IconFilter, IconMore, IconSend } from './Icons';

export default function ChatArea({ messages, isStreaming, mode, inputRef, messagesEndRef, onSend, onModeToggle }) {
  return (
    <div className="chat-area">
      <div className="chat-header" style={{ WebkitAppRegion: 'drag' }}>
        <span className="chat-title">Chat</span>
        <div className="header-toggles" style={{ WebkitAppRegion: 'no-drag' }}>
          <ModeToggle mode={mode} onToggle={onModeToggle} />
        </div>
        <div style={{ display: 'flex', gap: 2, WebkitAppRegion: 'no-drag' }}>
          <button className="icon-btn" title="Filter conversations"><IconFilter /></button>
          <button className="icon-btn" title="More options"><IconMore /></button>
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
                  {msg.text}
                  {msg.streaming && <span className="streaming-cursor">▊</span>}
                </div>
              </div>
            ))}
            {isStreaming && messages[messages.length - 1]?.text === '' && (
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
              placeholder="Message JARVIS..."
              disabled={isStreaming}
              className="chat-input"
            />
          </form>
          <div className="input-footer">
            <span className="input-disclaimer">JARVIS can be inaccurate, please double check its responses.</span>
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
