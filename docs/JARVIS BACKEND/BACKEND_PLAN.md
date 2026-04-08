# BACKEND_PLAN.md — JARVIS Backend Implementation Plan

**Owner:** Backend Implementor (Person 2 — Manideep)
**Stack:** Python 3.11 · FastAPI · WebSocket · Claude API · Ollama · Playwright · SQLite
**Build window:** 48 hours

---

## Guiding Principle

Backend's job is to be an invisible engine. The AI Lead writes prompts and tool schemas — you wire them up and make them run. The Frontend connects to your WebSocket and expects specific events — you send exactly those. The Integration Lead merges your PRs — you keep branches clean.

**You do not own prompts. You do not own UI. You do not own demo scripts.**
You own: `backend/` directory, all tool implementations, the WebSocket server, the Claude loop, and the AI router.

---

## Phase 1 — Foundation (Hours 0–18)

### Hour 0–1: Environment Setup
- [ ] Create Python 3.11 virtual environment: `python -m venv .venv && source .venv/bin/activate`
- [ ] Install all dependencies:
  ```bash
  pip install fastapi uvicorn anthropic httpx gitpython playwright watchdog pandas openpyxl jinja2
  playwright install chromium
  ```
- [ ] Read the WebSocket protocol in the Google Doc — ask all questions **now**
- [ ] Clone repo, create `backend/` folder structure:
  ```
  backend/main.py
  backend/ai/__init__.py
  backend/tools/__init__.py
  backend/memory/__init__.py
  backend/context/__init__.py
  ```
- [ ] Copy `.env.example` to `.env`, fill in your values

### Hour 1–2: Lock Contracts
- [ ] Review all 6 tool schemas with AI Lead — confirm every parameter is implementable
- [ ] Agree on final WebSocket event names (do not change after this hour)
- [ ] Confirm: what does `jarvis.json` look like? Backend reads it, never writes it
- [ ] **Output:** Written agreement with AI Lead. No surprises at Hour 8.

### Hour 2–4: FastAPI Server + WebSocket Echo
- [ ] `backend/main.py` — FastAPI app with CORS, lifespan startup
- [ ] WebSocket endpoint at `/ws`
- [ ] Echo server: receive JSON → send back the same JSON as `jarvis_reply`
- [ ] **Gate test:** Frontend can connect and receive an echo. Notify Integration Lead.

```python
# Minimum viable main.py structure
from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: launch file watcher task
    yield
    # shutdown: clean up

app = FastAPI(lifespan=lifespan)

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
        await websocket.send_json({"event": "jarvis_reply", "text": data.get("query"), "timestamp": ""})
```

### Hour 4–6: Basic Claude Call (No Tools)
- [ ] `backend/ai/claude_client.py` — `run(query, mode, ws)` function
- [ ] Hard-code `mode="cloud"` first (test only), switch to router later
- [ ] Single `client.messages.create()` call, stream the response back via `jarvis_reply` event
- [ ] Add `cache_control` to system prompt — do this from day one
- [ ] **Gate test:** Type a question, Claude replies in the UI. Show AI Lead.

### Hour 6–7: Prompt Caching
- [ ] Add `cache_control: { type: "ephemeral" }` to system prompt block
- [ ] Verify in Claude API response: `cache_creation_input_tokens > 0` on first call, `cache_read_input_tokens > 0` on second call
- [ ] This must be done before adding tools — caching only works on the system prompt position

### Hour 7–9: Tool-Use Loop
- [ ] `backend/ai/claude_client.py` — full agentic loop:
  ```
  send message → if stop_reason == "tool_use" → execute tool → send tool_result → repeat
  ```
- [ ] Wire in stub tools first (return mock data) — confirm the loop works
- [ ] Send `tool_call_status` events to WebSocket during tool execution
- [ ] **Critical:** `tool_use_id` always from `block.id` — never hardcode

```python
async def run(query: str, mode: str, ws: WebSocket) -> str:
    messages = [{"role": "user", "content": query}]
    
    while True:
        response = await call_claude(messages)
        
        if response.stop_reason == "end_turn":
            return extract_text(response)
        
        if response.stop_reason == "tool_use":
            tool_calls = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            
            for block in tool_calls:
                await ws.send_json({"event": "tool_call_status", "tool": block.name, "status": "start"})
                result = await execute_tool(block.name, block.input)
                await ws.send_json({"event": "tool_call_status", "tool": block.name, "status": "done"})
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,   # ← ALWAYS block.id
                    "content": str(result)
                })
            
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
```

### Hour 9–11: Codebase Reader + Git Interface
- [ ] `backend/tools/codebase_reader.py` — pathlib walk, respect `SKIP_DIRS`, 50 file / 200 line limits
- [ ] `backend/tools/git_interface.py` — gitpython: `repo.iter_commits(limit=n)`, `repo.head.commit.diff()`
- [ ] Both tools: never raise — always `return { "error": "..." }` on failure
- [ ] Test: ask "what files are in this project?" — Claude should call `read_codebase` and answer correctly
- [ ] **Show AI Lead sample outputs** from these tools before they write prompts for them

### Hour 11–13: Memory + Session Tools
- [ ] `backend/memory/jarvis_json.py` — `read()` and validate against schema in CLAUDE.md
- [ ] `backend/memory/session_log.py` — append-only JSON log of session summaries
- [ ] Wire both into tool dispatcher in `claude_client.py`
- [ ] Test: ask "what is this project about?" — Claude reads `jarvis.json` and gives a project-specific answer

### Hour 13–15: AI Router (Ollama Gate)
- [ ] `backend/ai/ollama_client.py` — POST to `http://localhost:11434/api/generate`
- [ ] `backend/ai/router.py` — if `mode == "local"` → try Ollama first, check confidence score against `OLLAMA_GATE_THRESHOLD`, escalate to Claude if below threshold
- [ ] Fallback: if Ollama is not running → log warning → route to Claude automatically
- [ ] Test: `AI_MODE=local` in `.env`, send a query — Ollama should handle it

### Hour 15–17: File Watcher
- [ ] `backend/context/file_watcher.py` — `watchdog` observer, debounce 5 seconds per file
- [ ] On relevant file change → ask Claude "A file changed: [path]. Is this relevant to the current session? If yes, surface it."
- [ ] Send `context_surface` event only if Claude says it's relevant
- [ ] Start in background via `asyncio.create_task(file_watcher.start())` in `lifespan`
- [ ] **This is the highest-risk feature.** Build it last in Phase 1 and keep it simple.

### Hour 17–18: Phase 1 Gate Review
- [ ] Integration Lead runs the full pipeline test
- [ ] All 6 tools registered and callable
- [ ] WebSocket sends all 6 event types correctly
- [ ] `AI_MODE=local` routes to Ollama by default
- [ ] No unhandled exceptions — all tools return dicts on failure

---

## Phase 2 — Intelligence Layer (Hours 18–28)

### Hour 18–20: Web Research Tool
- [ ] `backend/tools/web_research.py` — Playwright async: `async_playwright()`, launch chromium, `page.goto()`, `page.inner_text(selector or "body")`
- [ ] Timeout: 10 seconds. Always close browser in `finally:`. Return `{ "url", "content", "error" }`
- [ ] Test URLs provided by AI Lead (GitHub README, dev.to, Google Scholar)

### Hour 20–22: Report Generator Tool
- [ ] `backend/tools/report_generator.py` — Jinja2 `Environment`, load template from `templates/report.html`
- [ ] Accept `{ title, sections, output_path }` — render to HTML file — send `report_generated` event
- [ ] Coordinate with AI Lead on template variables before writing Jinja2 templates
- [ ] Test: call `generate_report` with mock data, verify HTML file is created, event is sent

### Hour 22–24: Streaming Responses
- [ ] Switch from `messages.create()` to `messages.stream()` for Claude calls
- [ ] Stream text tokens to WebSocket as `status_update` events while Claude is typing
- [ ] Full response still sent as `jarvis_reply` at the end
- [ ] Test: long query — user sees text appearing progressively

### Hour 24–26: Error Hardening
- [ ] Wrap every tool execution in try/except — tools never crash the main loop
- [ ] Add exponential backoff for Claude API 429 rate limit errors
- [ ] Graceful WebSocket disconnect handling: cleanup session on disconnect
- [ ] Log all errors to `backend/logs/error.log` with timestamp

### Hour 26–28: Ollama Gate Tuning
- [ ] Work with AI Lead on the Ollama confidence prompt
- [ ] The gate must correctly escalate: complex multi-tool queries → cloud, simple factual queries → local
- [ ] Test 10 sample queries, verify routing matches expected behavior
- [ ] **Share results with AI Lead** before finalizing thresholds

---

## Phase 3 — Polish & Demo Prep (Hours 28–36)

### Hour 28–30: Integration Testing
- [ ] Full pipeline test with Integration Lead
- [ ] Every demo scenario from the demo script must work end-to-end
- [ ] All WebSocket events arrive in the correct order
- [ ] Verify secure mode (local Ollama) works on the demo machine

### Hour 30–33: Performance Pass
- [ ] Measure response time for a typical query: target < 3 seconds for simple, < 8 seconds for tool-use
- [ ] If codebase_reader is slow: add file count cap, reduce depth default
- [ ] If Playwright is slow: reuse browser instance between calls instead of launching each time
- [ ] Profile and fix one bottleneck — don't optimize everything

### Hour 33–36: Demo Machine Setup
- [ ] Ensure `backend/` runs cleanly on the demo machine
- [ ] Ollama running in background, codellama model pulled
- [ ] `.env` has `ANTHROPIC_API_KEY` for cloud mode demo
- [ ] `uvicorn backend.main:app --host 0.0.0.0 --port 8000` starts without errors
- [ ] **Feature freeze at Hour 36 — no new features after this**

---

## Phase 4 — Demo Prep (Hours 36–48)

- [ ] **Hour 36–38:** Standby for demo rehearsal issues. Fix critical bugs only.
- [ ] **Hour 38–42:** Rest if possible. On call for backend bugs.
- [ ] **Hour 42–47:** Ensure Jarvis runs on demo machine. Verify Ollama running. Have `.env` with API key ready.
- [ ] **Hour 47–48:** No changes. Backend is done.

---

## Conflict Rules — How Backend Interacts With Other Roles

| Interface | Rule |
|---|---|
| **AI Lead → Backend** | AI Lead owns all prompt content and tool schemas. Backend implements exactly what the schema says. If a schema change is needed, ask AI Lead — never change a schema unilaterally. |
| **Backend → Frontend** | Frontend reads WebSocket events. Backend sends exactly the events listed in CLAUDE.md. If a new event type is needed, write it in CLAUDE.md first and get AI Lead + Frontend to acknowledge. |
| **Backend → Integration Lead** | All backend code goes into `backend/` directory only. PRs go through Integration Lead. Branch name: `backend/[feature]`. Merge conflicts in `backend/` are resolved by Backend — never by Integration Lead. |
| **Backend → Research+Docs** | Research+Docs sets up `jarvis.json` and Jinja2 templates. Backend reads `jarvis.json` but never modifies its structure. If `report_generator.py` needs a new template variable, tell Docs — never edit the template yourself. |
| **Demo machine** | Backend is responsible for verifying the server runs clean on the demo machine. Frontend is responsible for verifying the Electron app runs. Integration Lead owns the final sign-off. |

---

## What Backend Does NOT Own

- **Prompt content** in `prompts.py` — structure yes, content no (AI Lead owns)
- **Jinja2 templates** — `report_generator.py` calls the template, Docs writes the template
- **jarvis.json field values** — you read it, AI Lead + Docs fill it
- **Demo script** — that's Research+Docs
- **Frontend WebSocket client code** — that's Frontend
- **GitHub repo settings / branch protection** — that's Integration Lead

---

## Tech Reference

### pip install
```bash
pip install fastapi uvicorn anthropic httpx gitpython playwright watchdog pandas openpyxl jinja2
playwright install chromium
```

### Common Errors
| Error | Fix |
|---|---|
| `no current event loop` | Use `asyncio.get_event_loop().run_in_executor()` for sync code |
| `coroutine was never awaited` | Add `await` before the call |
| `400 from Claude API` | `tool_use_id` mismatch — check `block.id` |
| `429 rate limit` | Exponential backoff: wait 2s, 4s, 8s |
| `Claude ignores tools` | Pass `tools=` parameter on **every** API call |
| `Playwright timeout` | Increase `timeout=15000` or verify the URL loads manually |

### Build Order (Do Not Skip Steps)
```
Hour 2  → FastAPI server + WebSocket echo
Hour 4  → Basic Claude call (no tools)
Hour 6  → Prompt caching
Hour 7  → Tool-use loop
Hour 9  → codebase_reader + git_interface
Hour 11 → memory + session tools
Hour 13 → file watcher + Ollama gate
Hour 18 → web_research + report_generator
```
