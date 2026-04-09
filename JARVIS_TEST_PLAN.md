# JARVIS Feature Test Plan

Manual QA checklist for verifying every implemented feature before the Hour 36 feature freeze.

**How to use:** Run each test, compare actual output to the "Correct Output" column. Mark `PASS` or `FAIL`. Note any deviations.

---

## Prerequisites

Before running any tests, complete the startup sequence in this exact order:

```bash
# 1. Start Ollama (local AI gate) — required for local mode and proactive gate
ollama serve

# 2. Start backend
cd backend
python main.py
# Expected: FastAPI on http://localhost:8000, WebSocket on ws://localhost:8765

# 3. Start frontend Electron app
cd frontend
npm start
# Expected: Window opens with splash screen
```

**Required environment variables** (copy `.env.example` to `.env`):
| Variable | Required For | Value |
|----------|-------------|-------|
| `GEMINI_API_KEY` | Cloud mode (Gemini) | Your Gemini key |
| `GROQ_API_KEY` | Cloud mode (Groq fallback) | Your Groq key |
| `AI_MODE` | Default mode | `local` |
| `OLLAMA_GATE_THRESHOLD` | Proactive engine testing | `0.7` (lower to `0.1` for PROACTIVE-3) |

**Required tools:**
- Python 3.10+, Node.js, Ollama, `pip install playwright && playwright install chromium` (for TOOL-4)

---

## Section 1 — Infrastructure

### INFRA-1: Backend Starts Successfully

| Field | Detail |
|-------|--------|
| **Test** | Run `python main.py` in `backend/` directory |
| **Correct Output** | Console shows: `INFO: Application startup complete`, `WebSocket server started on port 8765`, `File watcher started on [project path]` |
| **Failure Signs** | Port already in use, import errors, missing `.env` keys |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### INFRA-2: Health Endpoint

| Field | Detail |
|-------|--------|
| **Test** | `curl http://localhost:8000/health` (run after frontend connects) |
| **Correct Output** | `{"status": "ok", "connected_clients": 1, "mode": "local", "codebase_loaded": true}` |
| **Notes** | `codebase_loaded` is `false` before first client connects. `connected_clients` matches actual number of connected Electron windows. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### INFRA-3: Codebase Scan on First Connect

| Field | Detail |
|-------|--------|
| **Test** | Open frontend app for the first time; watch backend terminal |
| **Correct Output** | Backend logs: `Codebase loaded: N files` (where N is the number of source files scanned, excluding node_modules, .git, etc.) |
| **Notes** | Subsequent connects do NOT re-scan (loaded once per process lifetime) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### INFRA-4: WebSocket Connection

| Field | Detail |
|-------|--------|
| **Test** | Run `python backend/test_ws_client.py` |
| **Correct Output** | Script connects, prints `Connected`, no errors in backend logs |
| **Failure Signs** | `ConnectionRefusedError`, `port 8765` errors |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 2 — Frontend / UI

### UI-1: Splash Screen — Connecting State

| Field | Detail |
|-------|--------|
| **Test** | Launch app BEFORE starting backend (`npm start` only, no `python main.py`) |
| **Correct Output** | Full black screen, "J.A.R.V.I.S" large title, amber/yellow pulsing dot, label reads "CONNECTING..." |
| **Notes** | App should NOT hang or crash — it keeps retrying WS every 2 seconds |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-2: Splash Screen — Connected State

| Field | Detail |
|-------|--------|
| **Test** | Start backend AFTER opening app (or restart app with backend already running) |
| **Correct Output** | Amber dot transitions to solid green dot, label changes to "READY", "START YOUR CONVO" button becomes active |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-3: Splash Screen — Enter Chat

| Field | Detail |
|-------|--------|
| **Test** | Click "START YOUR CONVO" button from splash screen |
| **Correct Output** | Splash screen fades out; main chat interface appears (sidebars visible, chat area with empty state) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-4: Hotkey Toggle — Show Overlay

| Field | Detail |
|-------|--------|
| **Test** | With app running, press `Ctrl+Space` from any window |
| **Correct Output** | Overlay window appears and chat input is focused (cursor inside input field) |
| **Notes** | If `Ctrl+Space` is taken by system, fallback is `Ctrl+Shift+Space` |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-5: Hotkey Toggle — Hide Overlay

| Field | Detail |
|-------|--------|
| **Test** | With overlay visible, press `Ctrl+Space` again |
| **Correct Output** | Overlay hides (window goes to background); no crash or error |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-6: System Tray — Right-Click Menu

| Field | Detail |
|-------|--------|
| **Test** | Right-click the JARVIS icon in the system tray (bottom-right taskbar) |
| **Correct Output** | Context menu appears with two items: "Open" and "Quit" (with separator between them) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-7: System Tray — Double Click

| Field | Detail |
|-------|--------|
| **Test** | Double-click the JARVIS tray icon |
| **Correct Output** | Window toggles visibility (shows if hidden, hides if visible) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-8: Chat Empty State

| Field | Detail |
|-------|--------|
| **Test** | Open chat with no messages sent yet |
| **Correct Output** | Large "J" circular avatar in center, text "How can I help you today?", input bar at bottom with placeholder text, no messages in message area |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-9: Sending a Message

| Field | Detail |
|-------|--------|
| **Test** | Type "Hello JARVIS" and press Enter (or click send button) |
| **Correct Output** | 1) User message "Hello JARVIS" appears as a bubble in chat. 2) Input field clears. 3) Input field becomes disabled/grayed out. 4) Send button becomes inactive. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-10: Streaming Response

| Field | Detail |
|-------|--------|
| **Test** | Send any message with backend connected and Ollama running |
| **Correct Output** | 1) "JARVIS is thinking…" text appears momentarily. 2) JARVIS response text streams in word-by-word. 3) Blinking block cursor `▊` visible at end of streaming text. 4) When done: cursor disappears, input re-enables. 5) Disclaimer "JARVIS can be inaccurate..." visible below input. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-11: Mode Toggle — Secure to Cloud

| Field | Detail |
|-------|--------|
| **Test** | Click the mode toggle pill in the chat header |
| **Correct Output** | 1) Toggle enters pending state (disabled, pulsing animation). 2) Dot slides right. 3) Color changes from green to blue. 4) Left sidebar connection indicator changes to green "ONLINE". 5) Toggle becomes interactive again within ~1 second. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-12: Mode Toggle — Cloud to Secure

| Field | Detail |
|-------|--------|
| **Test** | Click toggle again while in Cloud mode |
| **Correct Output** | Dot slides left, color returns to green, sidebar shows "OFFLINE" label |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-13: Error Message Display

| Field | Detail |
|-------|--------|
| **Test** | Stop the backend (`Ctrl+C` in backend terminal), then send a message from the UI |
| **Correct Output** | An inline error message appears in the chat area styled in red, e.g. "Unable to connect to JARVIS backend" or "Connection lost". Input re-enables after error. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-14: Surface Card Appearance

| Field | Detail |
|-------|--------|
| **Test** | Trigger via one of: (a) modify a `.py` file and wait for gate, or (b) run a test script that sends a `jarvis_surface` event directly |
| **Correct Output** | Card slides in from bottom-right with: file path/name in header, 2–3 bullet point suggestions, dismiss `✕` button |
| **Manual trigger for testing (run in Python):** | `python -c "import asyncio, websockets, json; asyncio.run(websockets.connect('ws://localhost:8765').__aenter__().send(json.dumps({'event':'jarvis_surface','file':'src/App.jsx','bullets':['Test bullet 1','Test bullet 2'],'reason':'test'})))"` |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-15: Surface Card — Auto-Dismiss (8 seconds)

| Field | Detail |
|-------|--------|
| **Test** | After surface card appears, do not interact with it |
| **Correct Output** | Card auto-dismisses after exactly 8 seconds; no lingering elements |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-16: Surface Card — Hover Pauses Timer

| Field | Detail |
|-------|--------|
| **Test** | When surface card appears, hover mouse over it at ~4 seconds |
| **Correct Output** | Card stays visible while hovering (timer paused); resumes countdown after mouse leaves; total display time = 8s of non-hover time |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-17: Surface Card — Manual Dismiss

| Field | Detail |
|-------|--------|
| **Test** | Click the `✕` button on the surface card |
| **Correct Output** | Card disappears immediately; `surface_dismissed` WebSocket event is sent to backend (verify in backend logs) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### UI-18: Report Toast

| Field | Detail |
|-------|--------|
| **Test** | Ask JARVIS: "Generate a report summarizing this project" (in Cloud mode for best results) |
| **Correct Output** | 1) Toast notification slides in at bottom-right. 2) Toast shows "Report ready — Open Report" (or similar). 3) Click "Open Report" → HTML file opens in system default browser. 4) Dismiss `✕` on toast closes it. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 3 — Chat & AI

### AI-1: Basic Query — Local Mode

| Field | Detail |
|-------|--------|
| **Test** | Ensure Secure mode is active. Ask: "What is this project about?" |
| **Correct Output** | Response mentions: JARVIS, the zero-search paradigm, developer context, and the tech stack (Electron, FastAPI, Ollama). Response is grounded in `jarvis.json` content. Backend logs show Ollama provider used. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-2: Basic Query — Cloud Mode

| Field | Detail |
|-------|--------|
| **Test** | Toggle to Cloud mode. Ask: "What is this project about?" |
| **Correct Output** | Same quality answer as AI-1. Backend logs show `groq` or `gemini` as the provider (NOT Ollama). |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-3: Streaming End-to-End (WebSocket Events)

| Field | Detail |
|-------|--------|
| **Test** | Open browser DevTools (or use `test_ws_client.py`) to monitor WebSocket frames. Send a message. |
| **Correct Output** | Multiple `jarvis_stream_chunk` events arrive with `{"event": "jarvis_stream_chunk", "text": "...", "done": false}`. Final event has `"done": true`. No separate `jarvis_response` event on the streaming path. A `status_update` event (`"Thinking..."`) arrives first. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-4: Context-Aware Response

| Field | Detail |
|-------|--------|
| **Test** | Ask: "What open questions does the team have?" |
| **Correct Output** | JARVIS lists the actual open questions from `jarvis.json` → `open_questions` array (e.g., cooldown window, max tool iterations, auto-dismiss timer). Must NOT hallucinate questions that aren't in the file. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-5: Fallback Chain (Gemini → Groq)

| Field | Detail |
|-------|--------|
| **Test** | Set `GEMINI_API_KEY=invalid_key_test` in `.env`. Restart backend. Switch to Cloud mode. Ask: "Diagnose an error: TypeError undefined is not a function" |
| **Correct Output** | Response still arrives (via Groq fallback). Backend logs show: `gemini failed` then `trying groq` then `using groq`. |
| **Cleanup** | Restore valid `GEMINI_API_KEY` after test |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-6: Backend Error → UI Error

| Field | Detail |
|-------|--------|
| **Test** | Kill backend (`Ctrl+C`). Send a message from UI. |
| **Correct Output** | UI shows red error message in chat. Input re-enables. No crash or frozen state. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### AI-7: Reconnect After Disconnect

| Field | Detail |
|-------|--------|
| **Test** | Kill backend, wait 10 seconds, restart backend. Then send a message. |
| **Correct Output** | Connection status indicator shows "CONNECTING..." while down, returns to "READY" within ~2 seconds of backend restart. Messages work normally after reconnect. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 4 — Tools

### TOOL-1: read_codebase — File Listing

| Field | Detail |
|-------|--------|
| **Test** | Ask: "List all the files in this project" |
| **Correct Output** | JARVIS responds with a list of source files (up to 50), organized by directory. Backend logs show `tool_call_status: read_codebase start/done`. Excluded dirs (node_modules, .git, __pycache__) NOT listed. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-2: read_codebase — Specific File

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Show me the contents of backend/main.py" |
| **Correct Output** | JARVIS returns the actual content of `backend/main.py` (up to 300 lines). Content matches what you'd see opening the file directly. Backend logs show `tool_call: read_codebase` with `file_path=backend/main.py`. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-3: read_codebase — Line Range

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Show me lines 50 to 100 of backend/main.py" |
| **Correct Output** | JARVIS returns only those specific lines (1-indexed). Content matches the actual file at those lines. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-4: read_git_history

| Field | Detail |
|-------|--------|
| **Test** | Ask: "What changed in git in the last 48 hours?" |
| **Correct Output** | JARVIS lists real commits with: short SHA (8 chars), commit message, author name, date. Matches output of `git log --since="48 hours ago"`. Backend logs show `tool_call: read_git_history`. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-5: web_research

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Research best practices for FastAPI WebSocket" (Cloud mode recommended) |
| **Prerequisite** | Playwright must be installed: `pip install playwright && playwright install chromium` |
| **Correct Output** | JARVIS returns summarized content from the web about FastAPI WebSockets. Backend logs show `tool_call: web_research start/done`. Content references real web information (not hallucinated). |
| **If Playwright not installed** | JARVIS returns an error message with install instructions — this is also an acceptable response (error handling working correctly) |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-6: generate_html_report

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Generate a report summarizing this project's architecture" (Cloud mode recommended) |
| **Correct Output** | 1) `reports/jarvis_report_[timestamp].html` file created on disk. 2) Backend sends `report_generated` WebSocket event. 3) Report toast appears in UI. 4) Opening the file shows valid HTML with the report content. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-7: update_project_memory — Append Decision

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Update project memory: we decided to set the surface card auto-dismiss to 8 seconds" |
| **Correct Output** | 1) JARVIS confirms the update in chat. 2) `jarvis.json` → `decisions` array has a new entry with `what`, `chose`, `rejected`, `reason` fields. 3) Open `jarvis.json` in editor to verify the new entry. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-8: update_project_memory — Update Focus

| Field | Detail |
|-------|--------|
| **Test** | Ask: "Update our current focus to: Testing and QA phase" |
| **Correct Output** | `jarvis.json` → `project.current_focus` changes to "Testing and QA phase". JARVIS confirms in chat. |
| **Cleanup** | Revert `current_focus` to original value after test |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### TOOL-9: read_session_history

| Field | Detail |
|-------|--------|
| **Test** | Ask: "What did we work on in previous sessions?" |
| **Correct Output** | JARVIS reads from `jarvis.json` → `session_log`. If empty, responds gracefully ("No previous sessions recorded"). If sessions exist, summarizes the last 3. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 5 — Proactive Engine

### PROACTIVE-1: File Watcher Starts

| Field | Detail |
|-------|--------|
| **Test** | Start backend, check terminal logs |
| **Correct Output** | Log entry: `File watcher started on [absolute path to project root]`. No errors. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### PROACTIVE-2: Gate Called on File Change

| Field | Detail |
|-------|--------|
| **Test** | Save any `.py` file in `backend/` (e.g., add a blank line and save `backend/main.py`) |
| **Correct Output** | Within 5 seconds, backend logs show: `Gate evaluating: [file path]` followed by `Gate result: {should_surface: [bool], confidence: [0-1], reason: "..."}` |
| **Notes** | Gate result can be `should_surface: false` — that's fine, it means the gate correctly decided not to surface |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### PROACTIVE-3: Surface Card Triggered by File Change

| Field | Detail |
|-------|--------|
| **Test** | Set `OLLAMA_GATE_THRESHOLD=0.1` in `.env` (restart backend). Save any `.py` or `.js` file. |
| **Correct Output** | Surface card appears in the UI within ~10–15 seconds of saving the file (gate time + surface generation time). Card has the saved file's path and 2–3 bullet points. |
| **Cleanup** | Restore `OLLAMA_GATE_THRESHOLD=0.7` |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### PROACTIVE-4: Debounce — Rapid Saves Ignored

| Field | Detail |
|-------|--------|
| **Test** | Save the same file 5 times quickly in under 5 seconds |
| **Correct Output** | Backend logs show gate called only ONCE (not 5 times). The `_last_event` debounce dict prevents repeated evaluations within the 5-second window. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### PROACTIVE-5: Ignored Directories

| Field | Detail |
|-------|--------|
| **Test** | Create/modify a file inside `node_modules/` or `.git/` |
| **Correct Output** | Backend does NOT log any gate evaluation for files in skip directories: `.git`, `__pycache__`, `node_modules`, `.venv`, `dist`, `build` |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### PROACTIVE-6: surface_dismissed Event Received

| Field | Detail |
|-------|--------|
| **Test** | After a surface card appears, click the `✕` dismiss button OR wait for 8s auto-dismiss |
| **Correct Output** | Backend logs: `surface_dismissed received for file: [file path]`. Event payload includes the file that was surfaced. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 6 — Mode Switching

### MODE-1: mode_change WebSocket Event

| Field | Detail |
|-------|--------|
| **Test** | Click mode toggle; watch backend logs |
| **Correct Output** | Backend logs: `Mode change requested: local → cloud` (or reverse). Then: `jarvis_mode_ack sent: {mode: "cloud"}`. Toggle goes from pending → active within ~1 second. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MODE-2: Local Mode — Ollama Only

| Field | Detail |
|-------|--------|
| **Test** | Ensure Secure mode. Send a query. Check backend logs. |
| **Correct Output** | Logs show `using provider: ollama`. No calls to `api.groq.com` or `generativelanguage.googleapis.com`. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MODE-3: Cloud Mode — Groq/Gemini Used

| Field | Detail |
|-------|--------|
| **Test** | Toggle to Cloud mode. Send a query. Check backend logs. |
| **Correct Output** | Logs show `using provider: groq` or `using provider: gemini`. Gate evaluations (from file watcher) still use Ollama regardless of mode. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MODE-4: Gate Always Uses Ollama

| Field | Detail |
|-------|--------|
| **Test** | While in Cloud mode, save a file to trigger gate |
| **Correct Output** | Backend logs show gate call goes to Ollama (`http://localhost:11434`), NOT to Groq/Gemini. The proactive gate is hardcoded to always use local Ollama regardless of mode. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Section 7 — Memory (jarvis.json)

### MEM-1: Context Read in System Prompt

| Field | Detail |
|-------|--------|
| **Test** | Ask: "What's our current project focus?" |
| **Correct Output** | JARVIS answers with the exact value in `jarvis.json` → `project.current_focus`. Currently: "Proactive developer intelligence — zero search paradigm" |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MEM-2: Decisions Read

| Field | Detail |
|-------|--------|
| **Test** | Ask: "What architectural decisions have we made?" |
| **Correct Output** | JARVIS lists the decisions from `jarvis.json` → `decisions` array. Each decision includes what was chosen and why. JARVIS does NOT invent decisions that aren't in the file. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MEM-3: Rejected Approaches Respected

| Field | Detail |
|-------|--------|
| **Test** | Ask JARVIS to suggest something that is in `jarvis.json` → `rejected_approaches` |
| **Correct Output** | JARVIS does NOT suggest the rejected approach. If asked about it directly, it explains it was considered and rejected (with the reason if available). |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MEM-4: jarvis.json Write + Read-Back

| Field | Detail |
|-------|--------|
| **Test** | Use TOOL-7 (update_project_memory) to add a test decision. Then ask JARVIS to list decisions. |
| **Correct Output** | The newly added decision appears in JARVIS's response. The change persists to disk (verify by opening `jarvis.json` in editor). |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

### MEM-5: Cache TTL (5 seconds)

| Field | Detail |
|-------|--------|
| **Test** | Send two messages in quick succession (< 5 seconds) both requiring jarvis.json. Check backend logs for disk reads. |
| **Correct Output** | First message triggers disk read (logged). Second message uses cached value (no disk read logged). Wait 6 seconds, send another message — cache expires and disk read happens again. |
| **Status** | `[ ] PASS / [ ] FAIL` |

---

## Test Summary

| Category | Total | Pass | Fail | Notes |
|----------|-------|------|------|-------|
| Infrastructure | 4 | | | |
| Frontend / UI | 18 | | | |
| Chat & AI | 7 | | | |
| Tools | 9 | | | |
| Proactive Engine | 6 | | | |
| Mode Switching | 4 | | | |
| Memory | 5 | | | |
| **TOTAL** | **53** | | | |

---

## Known Limitations & Acceptable Failures

| Test | Acceptable Condition |
|------|---------------------|
| TOOL-4 (web_research) | May fail if Playwright not installed — error message is acceptable output |
| TOOL-5 (generate_html_report) | Report renders minimal HTML if Jinja2 template at `backend/templates/report.html` is missing — minimal HTML is acceptable |
| AI-5 (Fallback chain) | Requires both `GEMINI_API_KEY` set and a cloud-billable task type to trigger Gemini path |
| PROACTIVE-3 (Surface trigger) | Requires Ollama running AND `OLLAMA_GATE_THRESHOLD` lowered; may take 10–20 seconds |
| AI-7 (Reconnect) | Reconnect is automatic at 2s flat interval; WS state in UI must reflect correctly |

---

*Last updated: 2026-04-09 | Branch: integration | Tested by: ________________*
