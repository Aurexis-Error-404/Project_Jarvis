# BACKEND_PLAN.md — JARVIS Backend Implementation Plan

**Owner:** Backend Implementor (Person 2 — Manideep)
**Stack:** Python 3.11 · FastAPI · WebSocket · Claude API · Ollama · Playwright · SQLite
**Build window:** 48 hours

> **See [CONFLICTS.md](./CONFLICTS.md) for 7 cross-doc discrepancies and their resolutions before starting any implementation.**

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Environment setup | ☐ Not started | |
| FastAPI + WebSocket server | ☐ Not started | |
| Claude client + tool-use loop | ☐ Not started | |
| Prompt caching | ☐ Not started | |
| `prompts.py` — system prompt builder | ☐ Not started | Uses `build_dynamic_context()` |
| `tool_dispatcher.py` | ☐ Not started | Routes Claude tool calls |
| `codebase_reader.py` | ☐ Not started | |
| `git_interface.py` | ☐ Not started | |
| `ollama_client.py` | ☐ Not started | Includes Ollama JSON parser |
| `router.py` — AI mode router | ☐ Not started | |
| `jarvis_json.py` — memory reader | ☐ Not started | |
| `session_log.py` | ☐ Not started | |
| `file_watcher.py` | ☐ Not started | Highest-risk feature |
| `web_research.py` (Playwright) | ☐ Not started | |
| `report_generator.py` (Jinja2) | ☐ Not started | |
| Streaming responses | ☐ Not started | |
| Error hardening | ☐ Not started | |

**Existing Python files:**
- `test_prompt.py` (root) — validates Claude API connectivity, prompt caching, Ollama connectivity. Run this first before writing any backend code to verify your environment.

---

## Guiding Principle

Backend's job is to be an invisible engine. The AI Lead writes prompts and tool schemas — you wire them up and make them run. The Frontend connects to your WebSocket and expects specific events — you send exactly those. The Integration Lead merges your PRs — you keep branches clean.

**You do not own prompts. You do not own UI. You do not own demo scripts.**
You own: `backend/` directory, all tool implementations, the WebSocket server, the Claude loop, and the AI router.

---

## Authoritative Sources (Resolve Conflicts Here)

| Topic | Authoritative Doc |
|-------|-------------------|
| Tool names + schemas | `prompts/tool_schema.md` |
| WebSocket events + payloads | `docs/JARVIS BACKEND/WEBSOCKET_PROTOCOL.md` |
| Port assignments | Root `CLAUDE.md` + `jarvis.json` |
| jarvis.json schema | Actual `jarvis.json` at repo root |
| Model routing | `prompts/model.md` |
| System prompt structure | `prompts/prompt_struc.md` |

---

## File Structure

```
backend/
├── main.py                    # FastAPI entry point — WebSocket at ws://localhost:8765
├── ai/
│   ├── __init__.py
│   ├── claude_client.py       # Tool-use loop — most critical file
│   ├── ollama_client.py       # Local model calls + Ollama JSON parser
│   ├── router.py              # AI_MODE routing: local vs cloud
│   └── prompts.py             # System prompt builder (AI Lead owns content)
├── tools/
│   ├── __init__.py
│   ├── codebase_reader.py     # read_codebase — file walker with limits
│   ├── git_interface.py       # read_git_history — gitpython wrapper
│   ├── web_research.py        # web_research — Playwright async scraper
│   ├── report_generator.py    # generate_html_report — Jinja2 HTML writer
│   └── tool_dispatcher.py     # Route tool_use blocks to implementations
├── memory/
│   ├── __init__.py
│   ├── jarvis_json.py         # Read + update jarvis.json (never free-write)
│   └── session_log.py         # Append-only session log
├── context/
│   ├── __init__.py
│   └── file_watcher.py        # Watchdog observer — proactive surface engine
├── logs/
│   └── error.log              # Timestamped error log
└── templates/
    └── report.html            # Jinja2 report template (Docs team writes this)
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
ANTHROPIC_API_KEY=sk-ant-...   # Never commit
AI_MODE=local                  # local | cloud — default to local during dev
OLLAMA_BASE_URL=http://localhost:11434
PROJECT_PATH=.                 # Path JARVIS monitors for the file watcher
OLLAMA_GATE_THRESHOLD=0.7      # Confidence below this → escalate to cloud
```

---

## Port Reference (LOCKED)

| Service | Address |
|---------|---------|
| FastAPI (REST) | `http://localhost:8000` |
| WebSocket server | `ws://localhost:8765` |
| Ollama | `http://localhost:11434` |

> WebSocket runs as a **separate server** on port 8765, NOT as `/ws` on FastAPI port 8000. See CONFLICTS.md #1 for details.

---

## Phase 1 — Foundation (Hours 0–18)

### Hour 0–1: Environment Setup

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install fastapi uvicorn anthropic httpx gitpython playwright watchdog pandas openpyxl jinja2 websockets
playwright install chromium
```

- Copy `.env.example` → `.env`, fill values
- Run `python test_prompt.py` to verify Claude API + caching + Ollama connectivity
- Create `backend/` folder structure

### Hour 2–4: FastAPI Server + WebSocket Echo

`backend/main.py`:
```python
import asyncio, json
from contextlib import asynccontextmanager
from fastapi import FastAPI
import websockets

connected_clients = set()

async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            await websocket.send(json.dumps({
                "event": "jarvis_reply",
                "text": f"Echo: {data.get('query')}",
                "timestamp": ""
            }))
    finally:
        connected_clients.remove(websocket)

async def start_ws_server():
    async with websockets.serve(ws_handler, "localhost", 8765):
        await asyncio.Future()  # run forever

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(start_ws_server())
    # asyncio.create_task(file_watcher.start())  # add at Hour 15
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Gate test:** Frontend connects to `ws://localhost:8765` and receives echo. Notify Integration Lead.

### Hour 4–6: Basic Claude Call (No Tools)

`backend/ai/claude_client.py`:
```python
import anthropic, os, datetime
from backend.ai.prompts import build_system_prompt

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def run(query: str, mode: str, send_event) -> str:
    await send_event({"event": "status_update", "message": "Thinking..."})

    system = build_system_prompt()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": query}]
    )
    text = response.content[0].text
    await send_event({
        "event": "jarvis_reply",
        "text": text,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    })
    return text
```

**Gate test:** Type a question → Claude replies in the UI. Show AI Lead.

### Hour 6–7: System Prompt Builder (`prompts.py`)

`backend/ai/prompts.py` — builds the two-block system prompt with caching.
Static block (identity + tool rules) is cached. Dynamic block (project context) is not.

```python
import json

STATIC_SYSTEM_PROMPT = """
<identity>
You are JARVIS — a proactive developer intelligence layer for a software project.
You have persistent memory of this project through jarvis.json.
You have access to 6 tools to retrieve live project context.

You are NOT a generic assistant. Every answer must be grounded in the project's
actual stack and decisions. If you don't have file content to support a claim,
say "I need to read [filename] first" and call read_codebase.
Never diagnose or recommend from general knowledge alone.
</identity>

<behavior_rules>
- Never say "according to your memory" or "based on the context provided" — just use it
- Never suggest technologies listed in rejected_approaches
- Never start responses with "I can see", "Based on", "Looking at", or "According to"
- Keep hotkey overlay responses under 100 words. Research reports can be long.
- Format error diagnosis exactly as: CAUSE / FIX / ALSO CHECK
- If decision sounds tentative ("thinking about", "maybe"): do NOT call update_project_memory
- If decision sounds committed ("we decided", "going with", "lock this in"): call update_project_memory
</behavior_rules>

<tool_rules>
- read_codebase: current code content, how something works, what a function does
- read_git_history: what changed recently, commit messages, bug introduction
- web_research: current information, research — always inject project-specific terms into query
- generate_html_report: ONLY after web_research, ONLY when developer explicitly asks for a report
- update_project_memory: ONLY on explicit commit phrases
- read_session_history: session start briefings, "where did we leave off"

Always use block.id for tool_use_id — never construct it manually.
Tools must never raise exceptions — return {"error": "message"} on failure.
</tool_rules>
"""

def build_system_prompt(jarvis_json_path: str = "jarvis.json",
                         codebase_map: str = "Codebase not yet read.",
                         session_history: str = "No session history loaded.") -> list:
    with open(jarvis_json_path) as f:
        j = json.load(f)

    decisions_text = "\n".join([
        f"- {d['what']}: chose {d['chose']}, rejected {d['rejected']} ({d['reason']})"
        for d in j.get("decisions", [])
    ])
    open_q_text = "\n".join([f"- {q}" for q in j.get("open_questions", [])])
    rejected_text = ", ".join(j.get("rejected_approaches", []))
    stack_text = ", ".join(j.get("project", {}).get("stack", []))

    dynamic_block = f"""<project_context>
Project: {j['project']['name']}
Stack: {stack_text}
Current focus: {j['project']['current_focus']}

Decisions made (never re-suggest alternatives):
{decisions_text}

Rejected approaches (never suggest): {rejected_text}

Open questions:
{open_q_text}
</project_context>

<codebase_map>
{codebase_map}
</codebase_map>

<recent_sessions>
{session_history}
</recent_sessions>"""

    return [
        {
            "type": "text",
            "text": STATIC_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}   # static — always cached
        },
        {
            "type": "text",
            "text": dynamic_block
            # no cache_control — changes every session
        }
    ]
```

**Verify caching:** After two calls, `response.usage.cache_read_input_tokens > 0`.
Token budget: system prompt must stay under 5,000 tokens total.

### Hour 7–9: Tool-Use Loop

Add to `backend/ai/claude_client.py`:

```python
from backend.tools.tool_dispatcher import dispatch_tool
from backend.tools import TOOL_SCHEMAS
from backend.ai import router

async def run(query: str, mode: str, send_event) -> str:
    await send_event({"event": "status_update", "message": "Thinking..."})

    system = build_system_prompt()
    messages = [{"role": "user", "content": query}]
    max_iter = int(os.environ.get("MAX_TOOL_ITERATIONS", 10))

    for _ in range(max_iter):
        response = client.messages.create(
            model=router.get_model(mode),
            max_tokens=2000,
            system=system,
            tools=TOOL_SCHEMAS,          # ALWAYS pass tools= on every call
            messages=messages
        )

        if response.stop_reason == "end_turn":
            text = next(b.text for b in response.content if hasattr(b, "text"))
            await send_event({
                "event": "jarvis_reply",
                "text": text,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
            })
            return text

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                await send_event({"event": "tool_call_status", "tool": block.name, "status": "start"})
                result = await dispatch_tool(block.name, block.input)
                await send_event({
                    "event": "tool_call_status",
                    "tool": block.name,
                    "status": "done",
                    "result_summary": str(result)[:100]
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,   # ALWAYS block.id — never construct
                    "content": str(result)
                })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    await send_event({"event": "error", "message": "Max tool iterations reached", "recoverable": True})
    return "I ran into a loop. Please try a more specific question."
```

`backend/tools/__init__.py` — paste the 6 tool schema dicts from `prompts/tool_schema.md`:
```python
TOOL_SCHEMAS = [
    # read_codebase, read_git_history, web_research,
    # generate_html_report, update_project_memory, read_session_history
]
```

`backend/tools/tool_dispatcher.py`:
```python
from backend.tools import codebase_reader, git_interface, web_research as web
from backend.tools import report_generator
from backend.memory import jarvis_json, session_log

async def dispatch_tool(name: str, inputs: dict) -> dict:
    try:
        if name == "read_codebase":
            return codebase_reader.run(**inputs)
        elif name == "read_git_history":
            return git_interface.run(**inputs)
        elif name == "web_research":
            return await web.run(**inputs)
        elif name == "generate_html_report":
            return report_generator.run(**inputs)
        elif name == "update_project_memory":
            return jarvis_json.update(**inputs)
        elif name == "read_session_history":
            return session_log.read(**inputs)
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}
```

### Hour 9–11: Codebase Reader + Git Interface

`backend/tools/codebase_reader.py` — parameters: `file_path`, `lines` (from tool_schema.md):
```python
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build"}
MAX_FILES = 50
MAX_LINES = 200

def run(file_path: str, lines: str = None) -> dict:
    try:
        root = Path(file_path)
        if file_path == ".":
            files = []
            for p in root.rglob("*"):
                if p.is_file() and not any(skip in p.parts for skip in SKIP_DIRS):
                    files.append(str(p))
                    if len(files) >= MAX_FILES:
                        break
            return {"files": files, "count": len(files)}
        else:
            p = Path(file_path)
            if not p.exists():
                return {"error": f"File not found: {file_path}"}
            content = p.read_text(encoding="utf-8", errors="ignore")
            if lines:
                start, end = map(int, lines.split("-"))
                content_lines = content.splitlines()
                content = "\n".join(content_lines[start-1:end])
            else:
                content_lines = content.splitlines()
                if len(content_lines) > MAX_LINES:
                    content = "\n".join(content_lines[:MAX_LINES]) + f"\n... (truncated at {MAX_LINES} lines)"
            return {"file": file_path, "content": content}
    except Exception as e:
        return {"error": str(e)}
```

`backend/tools/git_interface.py` — parameters: `since`, `include_diff`, `file_path` (from tool_schema.md):
```python
import git
from datetime import datetime, timedelta

def run(since: str, include_diff: bool = False, file_path: str = None) -> dict:
    try:
        repo = git.Repo(search_parent_directories=True)
        if since.endswith("h"):
            cutoff = datetime.now() - timedelta(hours=int(since[:-1]))
            commits = [c for c in repo.iter_commits(max_count=50)
                       if c.committed_datetime.replace(tzinfo=None) > cutoff]
        elif since.endswith("d"):
            cutoff = datetime.now() - timedelta(days=int(since[:-1]))
            commits = [c for c in repo.iter_commits(max_count=50)
                       if c.committed_datetime.replace(tzinfo=None) > cutoff]
        elif since.startswith("HEAD~"):
            n = int(since[5:])
            commits = list(repo.iter_commits(max_count=n))
        else:
            commits = list(repo.iter_commits(max_count=10))

        result = []
        for c in commits:
            entry = {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "author": str(c.author),
                "date": c.committed_datetime.isoformat()
            }
            if include_diff and c.parents:
                diff = repo.git.diff(c.parents[0].hexsha, c.hexsha)
                entry["diff"] = diff[:3000]
            result.append(entry)
        return {"commits": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e)}
```

**Test:** Ask "what files are in this project?" → Claude calls `read_codebase` and answers correctly.
Show AI Lead sample outputs from both tools before they finalize prompt descriptions.

### Hour 11–13: Memory + Session Tools

`backend/memory/jarvis_json.py`:
```python
import json
from pathlib import Path

JARVIS_PATH = Path("jarvis.json")

def read() -> dict:
    try:
        return json.loads(JARVIS_PATH.read_text())
    except Exception as e:
        return {"error": str(e)}

def update(field: str, action: str, value) -> dict:
    try:
        j = read()
        if "error" in j:
            return j
        if field == "decisions" and action == "append":
            j["decisions"].append(value)
        elif field == "open_questions" and action == "append":
            j["open_questions"].append(value)
        elif field == "open_questions" and action == "resolve":
            j["open_questions"] = [q for q in j["open_questions"] if q != value]
        elif field == "session_log" and action == "append":
            j["session_log"].append(value)
        elif field == "rejected_approaches" and action == "append":
            j["rejected_approaches"].append(value)
        elif field == "project.current_focus" and action == "update":
            j["project"]["current_focus"] = value
        else:
            return {"error": f"Unsupported field/action: {field}/{action}"}
        JARVIS_PATH.write_text(json.dumps(j, indent=2))
        return {"status": "updated", "field": field}
    except Exception as e:
        return {"error": str(e)}
```

`backend/memory/session_log.py`:
```python
from backend.memory.jarvis_json import read as read_jarvis

def read(last_n_sessions: int = 3) -> dict:
    try:
        j = read_jarvis()
        sessions = j.get("session_log", [])
        return {"sessions": sessions[-last_n_sessions:], "total": len(sessions)}
    except Exception as e:
        return {"error": str(e)}
```

**Test:** Ask "what is this project about?" → Claude reads `jarvis.json` via system prompt and gives a project-specific answer.

### Hour 13–15: AI Router (Ollama Gate)

`backend/ai/ollama_client.py` — includes the Ollama JSON parser (copy from `prompts/model.md`):
```python
import httpx, json, re, os

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = "codellama"
GATE_THRESHOLD = float(os.environ.get("OLLAMA_GATE_THRESHOLD", "0.7"))

GATE_PROMPT_TEMPLATE = """Respond with ONLY a JSON object. No other text.
No explanation. No code blocks. No markdown. Just the JSON:

{{"should_surface": true, "confidence": 0.8, "reason": "one sentence"}}

Signal: {signal_type} — {file_path}
Project focus: {current_focus}

JSON:"""

def parse_ollama_json(raw: str) -> dict:
    raw = re.sub(r'```(?:json)?\n?', '', raw).replace('```', '')
    match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if not match:
        return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}
    json_str = match.group()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            return json.loads(json_str.replace("'", '"'))
        except Exception:
            return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}

async def gate(signal_type: str, file_path: str, current_focus: str) -> dict:
    prompt = GATE_PROMPT_TEMPLATE.format(
        signal_type=signal_type, file_path=file_path, current_focus=current_focus
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(f"{OLLAMA_BASE_URL}/api/generate", json={
                "model": OLLAMA_MODEL, "prompt": prompt, "stream": False
            })
        return parse_ollama_json(r.json().get("response", ""))
    except Exception as e:
        return {"should_surface": False, "confidence": 0.0, "reason": f"ollama error: {e}"}
```

`backend/ai/router.py`:
```python
import os

def get_model(mode: str = None, task_type: str = "quick_qa") -> str:
    ai_mode = mode or os.environ.get("AI_MODE", "local")
    if ai_mode == "local":
        return "ollama/codellama"

    routing = {
        "research_report":  "claude-sonnet-4-20250514",
        "error_diagnosis":  "claude-sonnet-4-20250514",
        "git_summary":      "claude-haiku-4-5-20251001",
        "commit_message":   "claude-haiku-4-5-20251001",
        "session_summary":  "claude-haiku-4-5-20251001",
        "quick_qa":         "claude-haiku-4-5-20251001",
        "proactive_gate":   "ollama/codellama",   # never use cloud for gate
    }
    return routing.get(task_type, "claude-haiku-4-5-20251001")
```

**Fallback rule:** If Ollama is not running → log warning → route to Claude automatically.

### Hour 15–17: File Watcher

`backend/context/file_watcher.py`:
```python
import asyncio, time, os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from backend.ai import ollama_client
from backend.memory.jarvis_json import read as read_jarvis

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
DEBOUNCE_SECONDS = 5

class JarvisHandler(FileSystemEventHandler):
    def __init__(self, loop, send_event):
        self.loop = loop
        self.send_event = send_event
        self._last_event: dict[str, float] = {}

    def on_modified(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if any(skip in path for skip in SKIP_DIRS):
            return
        now = time.time()
        if now - self._last_event.get(path, 0) < DEBOUNCE_SECONDS:
            return
        self._last_event[path] = now
        asyncio.run_coroutine_threadsafe(self._evaluate(path), self.loop)

    async def _evaluate(self, path: str):
        jarvis = read_jarvis()
        focus = jarvis.get("project", {}).get("current_focus", "")
        result = await ollama_client.gate("file_modified", path, focus)
        threshold = float(os.environ.get("OLLAMA_GATE_THRESHOLD", "0.7"))
        if result.get("should_surface") and result.get("confidence", 0) >= threshold:
            await self.send_event({
                "event": "context_surface",
                "file": path,
                "reason": result.get("reason", "File modified — may affect active session")
            })

async def start(send_event):
    loop = asyncio.get_event_loop()
    handler = JarvisHandler(loop, send_event)
    observer = Observer()
    observer.schedule(handler, path=os.environ.get("PROJECT_PATH", "."), recursive=True)
    observer.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        observer.stop()
        observer.join()
```

**This is the highest-risk feature.** Build it last in Phase 1. Keep it simple — ship the gate call working before tuning the threshold.

### Hour 17–18: Phase 1 Gate Review

Checklist before handing off to Integration Lead:
- [ ] All 6 tools registered in `TOOL_SCHEMAS` and routed in `tool_dispatcher.py`
- [ ] WebSocket sends all 6 event types (status_update, tool_call_status, jarvis_reply, report_generated, context_surface, error)
- [ ] `AI_MODE=local` routes to Ollama by default
- [ ] No unhandled exceptions — all tools return `{"error": "..."}` on failure
- [ ] `test_prompt.py` still passes (regression check)

---

## Phase 2 — Intelligence Layer (Hours 18–28)

### Hour 18–20: Web Research Tool

`backend/tools/web_research.py` — parameter: `query` string (not a URL):
```python
from playwright.async_api import async_playwright

async def run(query: str, max_results: int = 5) -> dict:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=10000)
                content = await page.inner_text("body")
                return {"query": query, "content": content[:5000], "url": url}
            finally:
                await browser.close()
    except Exception as e:
        return {"error": str(e), "query": query}
```

Coordinate with AI Lead on test URLs before writing Playwright selectors.

### Hour 20–22: Report Generator Tool

`backend/tools/report_generator.py`:
```python
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import datetime

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def run(title: str, sections: list, research_data: str = "", output_path: str = None) -> dict:
    try:
        if output_path is None:
            ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_path = f"reports/jarvis_report_{ts}.html"
        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
        template = env.get_template("report.html")
        html = template.render(
            title=title, sections=sections,
            research_data=research_data,
            generated_at=datetime.datetime.utcnow().isoformat()
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html)
        return {"path": str(Path(output_path).absolute()), "html": html}
    except Exception as e:
        return {"error": str(e)}
```

`backend/templates/report.html` is written by the Docs team. Do not edit the template — only call it.
Coordinate with Docs on template variables (`title`, `sections`, `research_data`, `generated_at`) before they write the template.

### Hour 22–24: Streaming Responses

Switch from `messages.create()` to streaming:
```python
async def stream_response(query: str, mode: str, send_event) -> str:
    system = build_system_prompt()
    messages = [{"role": "user", "content": query}]
    full_text = ""

    with client.messages.stream(
        model=router.get_model(mode),
        max_tokens=2000,
        system=system,
        tools=TOOL_SCHEMAS,
        messages=messages
    ) as stream:
        for text in stream.text_stream:
            full_text += text
            await send_event({"event": "status_update", "message": text})

    await send_event({
        "event": "jarvis_reply",
        "text": full_text,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    })
    return full_text
```

### Hour 24–26: Error Hardening

- Wrap every tool in try/except (already done in `tool_dispatcher.py`)
- Exponential backoff for 429 errors:
  ```python
  import anthropic, asyncio
  for attempt in range(3):
      try:
          response = client.messages.create(...)
          break
      except anthropic.RateLimitError:
          wait = 2 ** attempt  # 2s, 4s, 8s
          await asyncio.sleep(wait)
  ```
- Graceful disconnect: cleanup session state in `finally:` block in `ws_handler`
- Log all errors with timestamp to `backend/logs/error.log`

### Hour 26–28: Ollama Gate Tuning

- Test 10 sample queries — verify routing matches expected behavior
- Complex multi-tool queries → cloud (confidence < 0.7)
- Simple factual queries → local
- Share results with AI Lead before finalizing `OLLAMA_GATE_THRESHOLD`

---

## Phase 3 — Polish & Demo Prep (Hours 28–36)

### Hour 28–30: Integration Testing

- Full pipeline test with Integration Lead
- Every demo scenario from demo script must work end-to-end
- All WebSocket events arrive in correct order
- Verify secure mode (local Ollama) works on demo machine

### Hour 30–33: Performance Pass

Target: simple query < 3 seconds, tool-use query < 8 seconds.

Likely bottlenecks:
- `codebase_reader`: add file count cap, reduce depth
- `web_research` Playwright: reuse browser instance between calls instead of launching each time

### Hour 33–36: Demo Machine Setup

- `pip install -r requirements.txt` runs clean
- Ollama running, `codellama` model pulled: `ollama pull codellama`
- `.env` has `ANTHROPIC_API_KEY` for cloud mode
- `uvicorn backend.main:app --host 0.0.0.0 --port 8000` starts without errors
- **Feature freeze at Hour 36 — no new features after this**

---

## Phase 4 — Demo Prep (Hours 36–48)

- **Hour 36–38:** Standby for demo rehearsal issues. Fix critical bugs only.
- **Hour 38–42:** Rest if possible. On call for backend bugs.
- **Hour 42–47:** Ensure Jarvis runs on demo machine. Ollama running. `.env` ready.
- **Hour 47–48:** No changes. Backend is done.

---

## Tool Implementation Guide

All 6 tools — exact names from `prompts/tool_schema.md` (authoritative source):

| Tool Name | Implements In | Key Parameters |
|-----------|--------------|----------------|
| `read_codebase` | `tools/codebase_reader.py` | `file_path` (relative path), `lines` (optional "80-120") |
| `read_git_history` | `tools/git_interface.py` | `since` ("24h", "HEAD~3"), `include_diff`, `file_path` |
| `web_research` | `tools/web_research.py` | `query`, `max_results` |
| `generate_html_report` | `tools/report_generator.py` | `title`, `sections`, `research_data`, `output_path` |
| `update_project_memory` | `memory/jarvis_json.py` | `field`, `action`, `value` |
| `read_session_history` | `memory/session_log.py` | `last_n_sessions` |

**Non-negotiables:**
- `tool_use_id` ALWAYS from `block.id` — never construct (`f"tool_{i}"` causes 400 error)
- Tools ALWAYS return `dict` — never raise exceptions out of a tool
- Pass `tools=TOOL_SCHEMAS` on EVERY Claude API call, not just the first

---

## WebSocket Event Reference

Server listens on `ws://localhost:8765` (separate from FastAPI on 8000).

| Event | When |
|-------|------|
| `status_update` | Immediately on query receive; during streaming |
| `tool_call_status` | On tool start + done (with `result_summary`) |
| `jarvis_reply` | Final response — always the last event in a query cycle |
| `report_generated` | After `generate_html_report` completes |
| `context_surface` | File watcher detects relevant change |
| `error` | Any failure (`recoverable: true/false`) |

Client sends: `{ "query": "string", "mode": "local|cloud" }`

---

## Common Errors

| Error | Fix |
|-------|-----|
| `no current event loop` | Use `asyncio.get_event_loop().run_in_executor()` for sync code |
| `coroutine was never awaited` | Add `await` before the call |
| `400 from Claude API` | `tool_use_id` mismatch — check `block.id` |
| `429 rate limit` | Exponential backoff: wait 2s, 4s, 8s |
| `Claude ignores tools` | Pass `tools=` on EVERY API call |
| `Playwright timeout` | Increase `timeout=15000` or verify URL manually |
| `Ollama JSON parse fails` | Use `parse_ollama_json()` from `ollama_client.py` |
| `cache_read_input_tokens == 0` | Never mutate the cached system prompt block between calls |
| `system prompt over 5000 tokens` | Truncate `codebase_map` to filenames only |

---

## Conflict Rules — How Backend Interacts With Other Roles

| Interface | Rule |
|-----------|------|
| **AI Lead → Backend** | AI Lead owns all prompt content and tool schemas (`prompts/`). Implement exactly what the schema says. Schema changes → ask AI Lead. |
| **Backend → Frontend** | Frontend reads WebSocket events at `ws://localhost:8765`. Backend sends exactly the 6 events listed above. New event type → update root CLAUDE.md first, get Frontend + AI Lead acknowledgement. |
| **Backend → Integration Lead** | All backend code in `backend/` only. PRs through Integration Lead. Branch: `backend/[feature]`. |
| **Backend → Docs** | Docs team owns `backend/templates/report.html`. Never edit the template — only call it. Coordinate on template variables before they write it. |
| **Demo machine** | Backend verifies server runs clean. Frontend verifies Electron. Integration Lead owns final sign-off. |

---

## What Backend Does NOT Own

- Prompt content in `prompts/` — AI Lead owns
- Jinja2 templates — Docs team writes them
- `jarvis.json` field values — AI Lead + Docs fill them
- Demo script — Docs/Research team
- Frontend WebSocket client — Frontend team
- GitHub repo settings — Integration Lead
