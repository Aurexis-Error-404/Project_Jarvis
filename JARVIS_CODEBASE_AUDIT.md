# JARVIS Codebase Audit Report

**Date:** 2026-04-11
**Branch:** `integration`
**Audited by:** Claude Code (automated analysis)

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 4 |
| Medium | 6 |
| Low | 8 |
| Recommendations | 5 |
| **Total** | **25** |

---

## Critical Issues

### CRIT-1: Malformed JSON Truncation Sent to LLM

**File:** `backend/ai/claude_client.py:340-342`
**Severity:** Critical

**Description:**
When tool output exceeds `MAX_TOOL_OUTPUT_CHARS` (12,000), the code truncates and appends `'..."}'`:

```python
result_json = _json.dumps(result, ensure_ascii=False, default=str)
if len(result_json) > MAX_TOOL_OUTPUT_CHARS:
    result_json = result_json[:MAX_TOOL_OUTPUT_CHARS] + '..."}'
```

This creates malformed JSON (e.g., `{"files": ["a.py", "b.py", "c..."}`) that gets sent back to the LLM as a tool result. The model may misinterpret the truncated data or reject the response.

**Impact:**
- LLM receives broken JSON, leading to incorrect analysis
- Could cause the model to hallucinate missing fields
- Particularly likely with `read_codebase(".")` on large projects (100 files = large JSON)

**Fix:**
```python
if len(result_json) > MAX_TOOL_OUTPUT_CHARS:
    result_json = _json.dumps({
        "truncated": True,
        "partial_data": result_json[:MAX_TOOL_OUTPUT_CHARS - 100],
        "note": f"Output truncated from {len(result_json)} chars. Ask for specific files instead of listing all."
    })
```

---

### CRIT-2: Unhandled Exception in System Prompt Construction

**File:** `backend/ai/prompts.py:118-124`
**Severity:** Critical

**Description:**
If `jarvis.json` is missing or malformed, the `build_system_prompt()` function crashes with an unhandled `FileNotFoundError` or `json.JSONDecodeError`:

```python
path = Path(jarvis_json_path)
if not path.exists():
    path = Path(__file__).parent.parent.parent / "jarvis.json"

with open(path) as f:      # Crashes if neither path exists
    j = json.load(f)        # Crashes if JSON is malformed
```

**Impact:**
- Every user query fails when jarvis.json is deleted or corrupted
- No fallback — the entire `run()` function raises, sending `jarvis_error` to the frontend
- The error message is a raw Python traceback, not user-friendly

**Fix:**
```python
try:
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error(f"Failed to load jarvis.json: {e}")
    j = {"project": {"name": "Unknown", "stack": [], "current_focus": "N/A"},
         "decisions": [], "open_questions": [], "rejected_approaches": []}
```

---

## High Severity Issues

### HIGH-1: Race Condition on `_current_mode` Global

**File:** `backend/main.py:30, 159`
**Severity:** High

**Description:**
`_current_mode` is a global string modified by any WebSocket handler on `mode_change` events (line 159). Multiple concurrent clients can race: Client A changes to "cloud", Client B reads "cloud" but expected "local".

The file watcher reads `_current_mode` via `get_mode=lambda: _current_mode` (line 290), which could see a stale or mid-transition value.

**Impact:**
- Client A could receive cloud responses when they're in local mode (or vice versa)
- File watcher routes to wrong provider

**Fix:** Protect `_current_mode` with `asyncio.Lock()` or make it per-connection state.

---

### HIGH-2: Sync Tools Run Without Timeout

**File:** `backend/tools/tool_dispatcher.py:43-47`
**Severity:** High

**Description:**
Async tools have a 60-second timeout via `asyncio.wait_for()`, but sync tools running in `run_in_executor()` have no timeout:

```python
# Async — has timeout:
return await asyncio.wait_for(_ASYNC_TOOLS[name](**inputs), timeout=60)

# Sync — NO timeout:
return await loop.run_in_executor(None, functools.partial(_SYNC_TOOLS[name], **inputs))
```

**Impact:**
- `read_codebase` on a massive directory, or `read_git_history` on a repo with 100K+ commits, could hang forever
- The UI shows the tool as "running" indefinitely
- Only fix is to kill the backend

**Fix:**
```python
return await asyncio.wait_for(
    loop.run_in_executor(None, functools.partial(_SYNC_TOOLS[name], **inputs)),
    timeout=60
)
```

---

### HIGH-3: Cloud Streaming Has No Timeout

**File:** `backend/ai/claude_client.py:210-223`
**Severity:** High

**Description:**
`_stream_final_response()` iterates over cloud streaming chunks with no timeout:

```python
async for chunk in stream:  # Blocks forever if stream stalls
    delta = chunk.choices[0].delta if chunk.choices else None
    ...
```

While the Ollama path was already fixed (gated to cloud-only), a stalled Gemini or Groq stream would still hang.

**Impact:**
- `isStreaming` permanently stuck at `true`, disabling the chat input
- Only recovery: close and reopen the app

**Fix:** Wrap the stream iteration in `asyncio.wait_for()`:
```python
async def _stream_with_timeout(stream, send_event, timeout=120):
    async def _consume():
        full_text = ""
        async for chunk in stream:
            ...
        return full_text
    return await asyncio.wait_for(_consume(), timeout=timeout)
```

---

### HIGH-4: Report Markdown Not Rendered

**File:** `backend/templates/report.html:78`
**Severity:** High (user-facing quality issue)

**Description:**
Section content is inserted with `{{ section.content | replace("\n", "<br>") }}`. Markdown formatting (`**bold**`, `*italic*`, `` `code` ``, `- bullets`) appears as literal text in the HTML output.

The tool schema says content is "Markdown content for this section" but no markdown processing happens.

**Impact:**
- Reports look unprofessional — bold text shows as `**text**`, code as backtick-wrapped
- Research data appears as raw JSON dump
- Users see a wall of unformatted text

**Status:** Fixed in this session — `report_generator.py` now processes markdown to HTML before template rendering.

---

## Medium Severity Issues

### MED-1: Missing Encoding in `prompts.py` File Read

**File:** `backend/ai/prompts.py:122`
**Severity:** Medium

`open(path)` without `encoding="utf-8"`. On Windows systems with non-UTF-8 locale, reading jarvis.json could produce garbled text or crash on non-ASCII characters (e.g., em dashes in decisions).

**Fix:** `with open(path, encoding="utf-8") as f:`

---

### MED-2: File Watcher Dict Race Condition

**File:** `backend/context/file_watcher.py:64-66`
**Severity:** Medium

The `_last_event` dictionary is accessed from watchdog threads and asyncio without synchronization. The eviction logic (`min()` over keys + `del`) is not atomic.

**Fix:** Use `threading.Lock()` or `asyncio.Lock()` to protect dict mutations.

---

### MED-3: `handleSelectProject` Missing Error Handling

**File:** `src/App.jsx:195`
**Severity:** Medium

```javascript
const handleSelectProject = useCallback(async () => {
    const dir = await window.jarvis?.selectProjectDir();
    if (dir) { sendMessage({ event: 'set_project_path', path: dir }); }
}, [sendMessage]);
```

No try-catch around the async IPC call. If Electron's dialog throws (e.g., system dialog crashes on some Linux DEs), the promise rejects silently.

**Fix:** Wrap in try-catch and dispatch an error message.

---

### MED-4: `_codebase_ready` Event Created Outside Lock

**File:** `backend/main.py:86-87`
**Severity:** Medium

```python
if _codebase_ready is None:
    _codebase_ready = asyncio.Event()  # Race: outside _codebase_lock
```

Two simultaneous first connections could both create an Event object. The 5-second timeout (line 132) mitigates this, but it's still a race.

**Fix:** Move inside `async with _codebase_lock:` block, or initialize at module level.

---

### MED-5: Conversation localStorage Could Grow Unbounded

**File:** `src/App.jsx` (conversations persistence)
**Severity:** Medium

Conversations are persisted to `localStorage` with no size cap. After months of use with long conversations, this could exceed localStorage limits (typically 5-10 MB).

**Fix:** Cap stored conversations to the most recent 50, or summarize old conversations before storage.

---

### MED-6: Incomplete `.env.example`

**File:** `.env.example`
**Severity:** Medium

Missing environment variables that the code reads:
- `OLLAMA_MODEL` (used in `providers.py:34`, `ollama_client.py:19`)
- `OLLAMA_BASE_URL` (used in `ollama_client.py:18`)
- `PROJECT_PATH` (used in tools after our fix)
- `MAX_TOOL_ITERATIONS` (used in `claude_client.py:28`)
- `OLLAMA_GATE_THRESHOLD` (used in `file_watcher.py:148`)
- `GEMINI_MODEL` (used in `providers.py:21`)
- `GROQ_MODEL` (used in `providers.py:27`)

**Fix:** Update `.env.example` with all used variables and defaults.

---

## Low Severity Issues

### LOW-1: Stale Closure in `onToggleOverlay` Effect

**File:** `src/App.jsx:111-115`

Empty dependency array `[]` means the `inputRef` callback captures the initial ref value. Since refs are mutable objects, this works in practice but violates React best practices.

---

### LOW-2: No Input Validation for Tool Arguments Type

**File:** `backend/ai/claude_client.py:318`

After `json.loads(tc.function.arguments)`, the code assumes the result is a dict. If Ollama returns `null`, a string, or an array, the `dispatch_tool(**inputs)` call will crash.

**Fix:** Add `if not isinstance(tool_input, dict)` guard.

---

### LOW-3: DOMPurify Allows `<div>` and `<span>` with `class` Attribute

**File:** `src/utils/renderMarkdown.js:31-37`

While `DOMPurify` is configured, allowing `class` attribute on `div`/`span` could enable CSS injection attacks if the AI generates malicious class names.

---

### LOW-4: Hardcoded WebSocket URL in Frontend

**File:** `src/App.jsx:53`

`useWebSocket('ws://localhost:8765')` — port is locked per CLAUDE.md, but this prevents deployment to non-localhost environments. Not a bug per current requirements, but limits future flexibility.

---

### LOW-5: Missing `.html` Extension Check in Report Opening

**File:** `preload.js:69-72`

The `openLocalFile` function checks the path is within `reports/` but the extension check could be more robust (e.g., `.HTML` vs `.html` on case-insensitive filesystems).

---

### LOW-6: `test_prompt.py` Uses Bare `except:`

**File:** `test_prompt.py:225, 228`

Bare `except:` clauses silently swallow all exceptions including `SystemExit` and `KeyboardInterrupt`, making debugging impossible.

---

### LOW-7: Missing Error Event for Codebase Load Failure

**File:** `backend/main.py:74-77`

If the codebase scan fails, it's only logged — no event is sent to the frontend. The user sees no indication that JARVIS doesn't know the codebase.

---

### LOW-8: Report Generator Jinja2 Autoescape Mismatch

**File:** `backend/tools/report_generator.py:62`

The Jinja2 environment uses `autoescape=True` but section content already contains HTML (from markdown processing). This double-escapes the content.

**Status:** Fixed in this session — changed to `autoescape=False` with pre-escaped title and research data.

---

## Recommendations

### REC-1: Add Structured Logging

Replace ad-hoc `logger.info()` with structured JSON logging (`python-json-logger`) to include request IDs, provider names, and durations for better observability.

### REC-2: Implement Circuit Breaker for Providers

If a provider fails 3+ times in 5 minutes, stop trying it for 10 minutes and go directly to fallback. Prevents hammering a rate-limited API.

### REC-3: Add API Cost Tracking

Wrap API calls with token counting. Log `{provider, model, tokens_in, tokens_out, estimated_cost}` to jarvis.json. Alert when approaching the $20 budget cap.

### REC-4: Add Rate Limiting on WebSocket Messages

No per-client rate limiting exists. A malicious or buggy frontend could spam `user_query` events. Add a simple token bucket (e.g., 10 queries per minute per client).

### REC-5: Validate jarvis.json Schema on Load

Use `jsonschema` or manual validation to catch corrupted jarvis.json files early, before they cause cryptic downstream errors.

---

## Files Audited

| File | Lines | Issues Found |
|------|-------|-------------|
| `backend/ai/claude_client.py` | 390 | 4 |
| `backend/ai/prompts.py` | 157 | 2 |
| `backend/ai/providers.py` | 121 | 1 |
| `backend/main.py` | 312 | 3 |
| `backend/tools/tool_dispatcher.py` | 61 | 1 |
| `backend/tools/codebase_reader.py` | 103 | 1 |
| `backend/tools/report_generator.py` | 99 | 1 |
| `backend/context/file_watcher.py` | 171 | 2 |
| `backend/ai/ollama_client.py` | 139 | 0 |
| `backend/memory/jarvis_json.py` | 114 | 0 |
| `src/App.jsx` | 260 | 3 |
| `src/components/ChatArea.jsx` | 110 | 0 |
| `src/utils/renderMarkdown.js` | 59 | 1 |
| `src/hooks/useWebSocket.js` | ~120 | 0 |
| `main.js` | 203 | 0 |
| `preload.js` | 93 | 2 |
| `.env.example` | 7 | 1 |
| `test_prompt.py` | ~230 | 1 |
