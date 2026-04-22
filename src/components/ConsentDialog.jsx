import { useEffect, useState } from 'react';

/**
 * ConsentDialog — blocking prompt for gated tools (§7.2).
 * Shows the action name and a summary of parameters the AI is about to
 * run, and waits for explicit approve/deny. Auto-denies on timeout so
 * a missed prompt can never be silently approved.
 */
export default function ConsentDialog({ request, onApprove, onDeny }) {
  const [secondsLeft, setSecondsLeft] = useState(request?.timeoutS || 30);

  useEffect(() => {
    if (!request) return undefined;
    setSecondsLeft(request.timeoutS || 30);
    const tick = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(tick);
          onDeny?.(request.requestId);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, [request, onDeny]);

  if (!request) return null;

  const entries = Object.entries(request.payload || {});

  return (
    <div className="consent-dialog-backdrop" role="dialog" aria-modal="true">
      <div className="consent-dialog">
        <h3 className="consent-title">Tool consent required</h3>
        <p className="consent-action">
          Action: <code>{request.action}</code>
        </p>
        {entries.length > 0 && (
          <dl className="consent-payload">
            {entries.map(([k, v]) => (
              <div key={k} className="consent-row">
                <dt>{k}</dt>
                <dd>{typeof v === 'string' ? v : JSON.stringify(v)}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="consent-timeout">Auto-denies in {secondsLeft}s</p>
        <div className="consent-buttons">
          <button
            type="button"
            className="consent-btn consent-deny"
            onClick={() => onDeny?.(request.requestId)}
          >
            Deny
          </button>
          <button
            type="button"
            className="consent-btn consent-approve"
            onClick={() => onApprove?.(request.requestId)}
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
