# JARVIS — Contracts Locked
**Locked: 2026-04-09 | Integration Lead sign-off required to change anything here.**

All teammates must acknowledge this file before writing business logic. React with ✅ in group chat when read.

---

## 1. WebSocket Endpoint

```
ws://localhost:8765
```
No path suffix. Backend: `websockets.serve(ws_handler, "localhost", 8765)`.

---

## 2. Message Field Name

All messages (frontend → backend AND backend → frontend) use **`event`** as the discriminator field.

```json
{ "event": "user_query", ... }
```

**Not** `type`, `action`, or `kind`. If you add a new event, use `event`.

---

## 3. Events: Frontend → Backend

| Event | Payload | Notes |
|-------|---------|-------|
| `user_query` | `{ event, query: string, mode: "local"\|"cloud" }` | Note: field is `query`, not `text` |
| `mode_change` | `{ event, mode: "local"\|"cloud" }` | Backend acks with `jarvis_mode_ack` |
| `surface_dismissed` | `{ event, file: string }` | Logged only, no response |

---

## 4. Events: Backend → Frontend

| Event | Payload | Notes |
|-------|---------|-------|
| `jarvis_response` | `{ event, text: string, timestamp: ISO }` | Full non-streamed response |
| `jarvis_stream_chunk` | `{ event, text: string, done: boolean }` | Streaming token; `done=true` signals end |
| `jarvis_surface` | `{ event, file: string, bullets: string[], reason: string, confidence: float }` | Proactive card |
| `jarvis_mode_ack` | `{ event, mode: "local"\|"cloud" }` | Confirms mode switch |
| `jarvis_error` | `{ event, message: string, recoverable: boolean }` | All errors use this name |
| `tool_call_status` | `{ event, tool: string, status: "start"\|"done", result_summary?: string }` | Tool progress |
| `status_update` | `{ event, message: string }` | Transient "Thinking..." message |
| `report_generated` | `{ event, path: string, html: string }` | Absolute file path to HTML report |

---

## 5. The 6 Locked Tool Names

These are the exact names Claude sees. Backend function names can differ; registered tool names cannot.

1. `read_codebase`
2. `read_git_history`
3. `web_research`
4. `generate_html_report`
5. `update_project_memory`
6. `read_session_history`

---

## 6. Locked Ports

| Service | Port | URL |
|---------|------|-----|
| WebSocket | 8765 | `ws://localhost:8765` |
| FastAPI | 8000 | `http://localhost:8000` |
| Ollama | 11434 | `http://localhost:11434` |

**Never change ports without updating both backend AND frontend simultaneously.**

---

## 7. AI Mode Values

- `"local"` — Ollama only. Zero bytes leave the machine. (SECURE MODE)
- `"cloud"` — Gemini (error_diagnosis, research_report) + Groq (everything else)
- Proactive gate: **always Ollama**, regardless of mode. Never cloud.

---

## 8. jarvis.json — Writable Fields

Backend **writes** to jarvis.json via the `update_project_memory` tool. It is **not** read-only.

Writable fields: `decisions`, `open_questions`, `session_log`, `project.current_focus`, `rejected_approaches`.

Write path: atomic via `p.write_text(json.dumps(...))` in `backend/memory/jarvis_json.py`.

---

## 9. Startup Order

```bash
ollama serve                      # 1. Local AI gate (must be up before backend)
cd backend && python main.py      # 2. FastAPI + WebSocket on :8000 / :8765
npm start                         # 3. Electron (builds bundle then launches)
```

---

## 10. Conflict History (resolved)

| Conflict | Resolution |
|----------|------------|
| WebSocket port 8000 vs 8765 | **8765** (three of four sources agreed) |
| `event` vs `type` field | **`event`** (backend was authoritative) |
| `text` vs `query` for user message | **`query`** (backend reads `data.get("query")`) |
| `jarvis_reply` vs `jarvis_response` | **`jarvis_response`** (backend implementation) |
| `mode_change` vs `set_mode` | **`mode_change`** (backend implementation) |
| jarvis.json read-only vs writeable | **Writeable** via tool (tool contract wins) |
| `generate_report` vs `generate_html_report` | **`generate_html_report`** (tool_schema.md) |
| `"event": "error"` in claude_client.py | Fixed to **`"event": "jarvis_error"`** |
