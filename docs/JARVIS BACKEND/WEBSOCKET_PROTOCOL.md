# WEBSOCKET_PROTOCOL.md — JARVIS WebSocket Protocol

**Status: LOCKED after Hour 2. No changes without AI Lead + Backend + Frontend agreement.**

---

## Connection

```
URL:      ws://localhost:8000/ws
Protocol: JSON over WebSocket
Auth:     None (local-only app)
```

---

## Client → Server (Frontend sends this)

```json
{
  "query": "string — the user's message",
  "mode": "local | cloud"
}
```

No other fields. Frontend must always send `mode`. Default: `"local"`.

---

## Server → Client (Backend sends these)

### 1. `status_update` — Loading indicator
Sent immediately after receiving a query. Use to show "Thinking..." in the UI.

```json
{
  "event": "status_update",
  "message": "Thinking..."
}
```

### 2. `tool_call_status` — Tool execution update
Sent once when a tool starts, once when it completes.

```json
{
  "event": "tool_call_status",
  "tool": "read_codebase",
  "status": "start"
}
```
```json
{
  "event": "tool_call_status",
  "tool": "read_codebase",
  "status": "done",
  "result_summary": "Read 23 files"
}
```

### 3. `jarvis_reply` — Final AI response
The complete response. Always the last event in a query cycle.

```json
{
  "event": "jarvis_reply",
  "text": "Here is what I found in your codebase...",
  "timestamp": "2026-04-07T10:30:00Z"
}
```

### 4. `report_generated` — Report file created
Sent after `generate_report` tool completes.

```json
{
  "event": "report_generated",
  "path": "/absolute/path/to/report.html",
  "html": "<html>...</html>"
}
```

### 5. `context_surface` — File watcher alert
Sent when the file watcher detects a relevant change.

```json
{
  "event": "context_surface",
  "file": "backend/ai/claude_client.py",
  "reason": "File modified — this may affect the active session"
}
```

### 6. `error` — Something went wrong
Sent on any unhandled error.

```json
{
  "event": "error",
  "message": "Claude API rate limit exceeded",
  "recoverable": true
}
```

`recoverable: true` means the user can retry. `recoverable: false` means a restart may be needed.

---

## Event Sequence (Normal Query)

```
Client → Server:  { query: "...", mode: "local" }

Server → Client:  { event: "status_update", message: "Thinking..." }
Server → Client:  { event: "tool_call_status", tool: "read_codebase", status: "start" }
Server → Client:  { event: "tool_call_status", tool: "read_codebase", status: "done", result_summary: "..." }
Server → Client:  { event: "status_update", message: "Generating response..." }
Server → Client:  { event: "jarvis_reply", text: "...", timestamp: "..." }
```

---

## Event Sequence (Report Generation)

```
Client → Server:  { query: "Generate a project report", mode: "cloud" }

Server → Client:  { event: "status_update", message: "Thinking..." }
Server → Client:  { event: "tool_call_status", tool: "read_codebase", status: "start" }
Server → Client:  { event: "tool_call_status", tool: "read_codebase", status: "done" }
Server → Client:  { event: "tool_call_status", tool: "generate_report", status: "start" }
Server → Client:  { event: "tool_call_status", tool: "generate_report", status: "done" }
Server → Client:  { event: "report_generated", path: "...", html: "..." }
Server → Client:  { event: "jarvis_reply", text: "Report generated at ...", timestamp: "..." }
```

---

## Error Handling Contract

- Backend guarantees that `jarvis_reply` is always sent, even on error (the error event is sent first, then a fallback reply)
- Frontend must handle all 6 event types — unknown events should be silently ignored
- If WebSocket disconnects, Frontend should retry after 2 seconds with exponential backoff
- Backend cleans up session state on disconnect
