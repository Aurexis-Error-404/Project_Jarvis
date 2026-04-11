# JARVIS Issues Report

**Date:** 2026-04-11
**Branch:** `integration`
**Sprint:** 48-hour (Hour 36 feature freeze)

---

## Critical Bugs

### BUG-1: Tools ignore selected project path

**Severity:** Critical
**Status:** Fixed
**Files:** `backend/tools/codebase_reader.py:38,56` | `backend/tools/git_interface.py:25`

**Description:**
After clicking "Add Project" and selecting an external directory, JARVIS still reads files from its own repo. The codebase reader and git history tools hardcode their root to `Path(".")` (current working directory), ignoring the `PROJECT_PATH` environment variable set by the backend when a user selects a project.

**Root Cause:**
- `codebase_reader.py` line 38: `root = Path(".")` — always lists files from CWD
- `codebase_reader.py` line 56: `p = Path(file_path)` — resolves paths relative to CWD
- `git_interface.py` line 25: `git.Repo(search_parent_directories=True)` — searches from CWD upward

The backend's `set_project_path` handler (`main.py:199`) correctly sets `os.environ["PROJECT_PATH"]` and reloads the codebase map, but no tool ever reads this variable.

**Impact:**
- "Add Project" button appears to work (codebase map updates) but all tool calls (file reads, git history) still operate on the JARVIS repo
- Users cannot analyze any project other than JARVIS itself

**Fix Applied:**
- `codebase_reader.py`: `_list_files()` and `_read_file()` now resolve paths relative to `os.environ.get("PROJECT_PATH", ".")`
- `git_interface.py`: `git.Repo()` now receives `PROJECT_PATH` as its search root

---

### BUG-2: Conversations lost on app restart

**Severity:** Critical
**Status:** Fixed
**Files:** `src/App.jsx:23`

**Description:**
All conversation history disappears when the Electron app is closed and reopened, or when the page reloads. The sidebar shows no previous conversations after restart.

**Root Cause:**
- `App.jsx` line 23: `const [conversations, setConversations] = useState([])` — conversations are stored only in React state (in-memory)
- No persistence mechanism saves conversations to disk or localStorage
- The `reports` list (line 19) uses localStorage for persistence, but conversations do not follow the same pattern

**Impact:**
- Users lose all conversation history on every restart
- Cannot reference or continue previous conversations
- Sidebar conversation list always starts empty

**Fix Applied:**
- `conversations` state now initializes from `localStorage.getItem('jarvis_conversations')` using the same lazy-init pattern as `reports`
- Added `useEffect` to persist `conversations` to localStorage on every change

---

### BUG-3: Session history not passed to AI system prompt

**Severity:** High
**Status:** Fixed
**Files:** `backend/ai/claude_client.py:221` | `backend/ai/prompts.py:109`

**Description:**
JARVIS has no awareness of previous sessions when answering questions. Even though the system prompt template includes a `<recent_sessions>` block, it is never populated with actual session data.

**Root Cause:**
- `prompts.py` line 109: `build_system_prompt()` accepts a `session_history` parameter and injects it into the `<recent_sessions>` block (line 152-154)
- `claude_client.py` line 221: calls `prompts.build_system_prompt(codebase_map=codebase_map)` — never passes `session_history`
- The default value `"No session history loaded."` is always used
- `session_log.py` has a working `read()` function that returns session metadata, but it's never called during prompt construction

**Impact:**
- AI cannot answer "what did we work on before?" or provide session continuity
- The `read_session_history` tool can fetch the data, but the system prompt never primes the AI with session context

**Fix Applied:**
- Added `_format_session_history()` helper to `claude_client.py` that reads `session_log` and formats it
- `build_system_prompt()` now receives the formatted session history on every query

---

## Secondary Bugs

### BUG-4: Sync tools have no execution timeout

**Severity:** Medium
**Status:** Open
**Files:** `backend/tools/tool_dispatcher.py:43-47`

**Description:**
Synchronous tools (`read_codebase`, `read_git_history`, `update_project_memory`, `read_session_history`) run in a thread executor without any timeout. Async tools (`web_research`, `generate_html_report`) have a 60-second timeout via `asyncio.wait_for()`.

**Root Cause:**
```python
# Async tools — have timeout:
return await asyncio.wait_for(_ASYNC_TOOLS[name](**inputs), timeout=60)

# Sync tools — NO timeout:
return await loop.run_in_executor(None, functools.partial(_SYNC_TOOLS[name], **inputs))
```

**Impact:**
- If a sync tool hangs (e.g., `git.Repo()` on a massive repo, or `_list_files()` on a directory with millions of files), the entire query hangs indefinitely
- The UI shows the tool as "running" forever with no way to cancel

**Proposed Fix:**
Wrap the `run_in_executor` call with `asyncio.wait_for(..., timeout=60)`.

---

### BUG-5: Cloud streaming response has no timeout

**Severity:** Medium
**Status:** Open
**Files:** `backend/ai/claude_client.py:193`

**Description:**
The `_stream_final_response()` function iterates over streaming chunks with `async for chunk in stream` but has no timeout guard. If a cloud provider's stream stalls without closing, the function blocks forever.

**Root Cause:**
```python
async for chunk in stream:  # No timeout — blocks forever if stream stalls
    delta = chunk.choices[0].delta if chunk.choices else None
    ...
```

Note: The local/Ollama streaming path was already fixed (gated to cloud-only in the previous commit), but the cloud path still has no timeout.

**Impact:**
- A stalled Gemini or Groq stream would permanently lock `isStreaming=true`, disabling the chat input
- The only recovery is killing and restarting the app

**Proposed Fix:**
Wrap the streaming loop in `asyncio.wait_for(..., timeout=120)` with a fallback to `_stream_text()`.

---

### BUG-6: Chat input not disabled when WebSocket disconnected

**Severity:** Low
**Status:** Fixed
**Files:** `src/components/ChatArea.jsx:85` | `src/App.jsx`

**Description:**
When the backend goes down, the chat input remains enabled. Users can type and submit messages that silently fail (WebSocket is disconnected, messages are dropped).

**Root Cause:**
- `ChatArea.jsx` line 85: `disabled={isStreaming}` — only checks streaming state, not connection status
- `connectionStatus` was not passed as a prop to `ChatArea`

**Impact:**
- Users send messages into the void when backend is down
- No visual feedback that the connection is lost (sidebar shows status but input doesn't reflect it)

**Fix Applied:**
- `connectionStatus` prop passed from `App.jsx` to `ChatArea`
- Input now disabled when `connectionStatus !== 'connected'`

---

### BUG-7: Codebase Event race condition on simultaneous connections

**Severity:** Low
**Status:** Open
**Files:** `backend/main.py:86-87`

**Description:**
The `_codebase_ready` asyncio.Event is created inside `ws_handler` on the first connection, but the creation happens outside the `_codebase_lock`. Two simultaneous first connections could both execute `_codebase_ready = asyncio.Event()`, with one overwriting the other's Event.

**Root Cause:**
```python
async def ws_handler(websocket):
    global _codebase_ready
    if _codebase_ready is None:
        _codebase_ready = asyncio.Event()  # RACE: outside lock
    # ...
    async with _codebase_lock:
        if not _codebase_loaded:
            # ...
```

**Impact:**
- Extremely unlikely in practice (requires two clients to connect simultaneously on first startup)
- If it occurs: one client waits on an Event that never gets `.set()`, hanging for up to 5 seconds (the timeout catches this)
- Non-critical because the 5-second timeout provides a safety net

**Proposed Fix:**
Move `_codebase_ready` initialization inside the lock, or initialize it at module level (requires the asyncio event loop to be running).

---

## Summary

| # | Title | Severity | Status |
|---|-------|----------|--------|
| 1 | Tools ignore PROJECT_PATH | Critical | **Fixed** |
| 2 | Conversations lost on restart | Critical | **Fixed** |
| 3 | Session history not in prompt | High | **Fixed** |
| 4 | Sync tools no timeout | Medium | Open |
| 5 | Cloud streaming no timeout | Medium | Open |
| 6 | Input enabled when disconnected | Low | **Fixed** |
| 7 | Codebase Event race condition | Low | Open |

**4 bugs fixed** | **3 bugs documented** (open — non-blocking for feature freeze)
