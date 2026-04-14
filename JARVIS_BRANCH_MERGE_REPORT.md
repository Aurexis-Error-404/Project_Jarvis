# JARVIS Branch Merge Report

**Date:** 2026-04-12
**Branches compared:** `integration` vs `new`
**Goal:** Merge both branches to get the best of each — architectural refactoring from `new`, bug fixes from `integration`

---

## Executive Summary

The two branches evolved independently and represent complementary work:

| Branch | Character | What it adds |
|--------|-----------|-------------|
| `integration` | **Bug fixes & features** | PROJECT_PATH support, conversation persistence, session history injection, disconnect input guard, redesigned reports, Markdown rendering, audit docs |
| `new` | **Architecture & structure** | Frontend refactor (hooks/constants extracted), CSS split, Electron restructure, backend handler extraction, wiki, improved useWebSocket reconnect logic |

Neither branch is "better" — the correct approach is to merge architectural patterns from `new` onto the feature work in `integration`. The `new` branch contains **2 unresolved merge conflicts** that must be resolved before it can build.

---

## Part 1 — Conflicts in the `new` Branch (Must Fix First)

These are live conflict markers (`<<<<<<<`/`>>>>>>>`) in files on the `new` branch that prevent a clean build.

---

### CONFLICT-1: `src/App.jsx`

**Nature:** Two different approaches to conversation state management.

**`new` branch approach (HEAD):**
- Conversations extracted into `useConversations` custom hook
- Hook owns the state, provides `autoTitle`, `syncMessages`, `selectConv`, `newSession`
- App.jsx is lean — just calls hook, no inline conversation logic

**`integration` branch approach (e389db3):**
- Conversations in local `useState` inside App.jsx
- localStorage persistence via `useEffect`
- `handleSelectConv` and `handleNewSession` inline in App.jsx

**Conflict location 1 (lines 23-30):**
```
<<<<<<< HEAD
=======
  const [conversations, setConversations] = useState(() => {
    try { return JSON.parse(localStorage.getItem('jarvis_conversations') || '[]'); }
    catch { return []; }
  });
  const [activeConvId, setActiveConvId] = useState(null);
>>>>>>> e389db3
```

**Conflict location 2 (lines 42-49):**
```
<<<<<<< HEAD
  const { conversations, activeConvId, autoTitle, syncMessages, selectConv, newSession } = useConversations({...});
=======
  // Persist conversations across restarts
  useEffect(() => {
    localStorage.setItem('jarvis_conversations', JSON.stringify(conversations));
  }, [conversations]);
  ...
>>>>>>> e389db3
```

**Resolution (keep `new` hook but add localStorage to it):**

The `new` branch's `useConversations` hook in `src/hooks/useConversations.js` initializes with `useState([])` — no persistence. The `integration` branch adds persistence. The correct merge is to add localStorage to the hook, not keep it in App.jsx.

Edit `src/hooks/useConversations.js` — change the `useState([])` initialization:
```javascript
// Before (new branch):
const [conversations, setConversations] = useState([]);

// After (merged):
const [conversations, setConversations] = useState(() => {
  try { return JSON.parse(localStorage.getItem('jarvis_conversations') || '[]'); }
  catch { return []; }
});

// Add persistence effect inside the hook:
useEffect(() => {
  localStorage.setItem('jarvis_conversations', JSON.stringify(conversations));
}, [conversations]);
```

Then in `App.jsx`, **keep only the `new` branch version** (use the hook, discard the `integration` inline state).

---

### CONFLICT-2: `src/components/ChatArea.jsx`

**Nature:** Two different input handling patterns.

**`new` branch approach (HEAD):**
- Controlled input: `const [inputValue, setInputValue] = useState('')`
- Input identified by `id="jarvis-input"` (not by `ref`)
- `inputRef` is virtualized: `inputRef.current = { focus: () => document.getElementById('jarvis-input')?.focus() }`
- `submit()` function uses `inputValue` state
- Send button only disabled on `isStreaming` (missing `connectionStatus` guard)

**`integration` branch approach (e389db3):**
- Uncontrolled input via `ref={inputRef}`
- `connectionStatus` prop accepted and used on both input and send button
- No controlled state in ChatArea

**Conflict location 1 (lines 15-33) — component signature:**
```
<<<<<<< HEAD
export default function ChatArea({ ..., activeTools = [] }) {
  const [inputValue, setInputValue] = useState('');
  useEffect(() => { /* virtualize inputRef */ }, [inputRef]);
  const submit = () => { ... };
=======
export default function ChatArea({ ..., activeTools = [], connectionStatus }) {
>>>>>>> e389db3
```

**Conflict location 2 (lines 89-101) — send button:**
```
<<<<<<< HEAD
<button className="btn-send" disabled={isStreaming} onClick={submit}>
=======
<button className="btn-send"
  disabled={isStreaming || connectionStatus !== 'connected'}
  onClick={() => { const val = inputRef.current?.value?.trim(); ... }}>
>>>>>>> e389db3
```

**Resolution (keep `new` controlled input, add `connectionStatus` guard):**

The `new` branch's controlled input is architecturally better (no uncontrolled state, clearer submit flow). Add `connectionStatus` from `integration` as a prop:

```javascript
// Final resolved ChatArea signature:
export default function ChatArea({
  messages, isStreaming, mode, inputRef, messagesEndRef,
  onSend, onModeToggle, activeTools = [], connectionStatus
}) {
  const [inputValue, setInputValue] = useState('');

  useEffect(() => {
    if (inputRef) {
      inputRef.current = { focus: () => document.getElementById('jarvis-input')?.focus() };
    }
  }, [inputRef]);

  const submit = () => {
    const val = inputValue.trim();
    if (val && !isStreaming) { onSend(val); setInputValue(''); }
  };

  // ... render ...
  // Input:
  disabled={isStreaming || connectionStatus !== 'connected'}
  // Send button:
  disabled={isStreaming || connectionStatus !== 'connected'}
```

---

## Part 2 — What `new` Has That `integration` Lacks

These are improvements in `new` that should be brought forward.

---

### NEW-1: Frontend constants centralized

**Files:** `src/constants/config.js`, `src/constants/wsEvents.js`

`config.js` defines timing magic numbers and the WS_URL in one place:
```javascript
export const WS_URL            = 'ws://localhost:8765';
export const SPLASH_DISMISS_MS = 1_500;
export const TOOL_DONE_REMOVE_MS = 1_500;
export const INPUT_FOCUS_MS    = 50;
```

`wsEvents.js` defines all event strings as constants:
```javascript
export const RECV = {
  STREAM_CHUNK: 'jarvis_stream_chunk',
  ERROR: 'jarvis_error',
  // ...
};
```

**Why it matters:** Magic strings like `'jarvis_stream_chunk'` are scattered across 4+ files in `integration`. One typo = silent failure.

**Action:** Copy both files from `new` to `integration` and update imports.

---

### NEW-2: `useJarvisEvents` — event handler extraction

**File:** `src/hooks/useJarvisEvents.js`

All `onStreamChunk`, `onResponse`, `onError`, `onToolCallStatus` etc. handlers are extracted from App.jsx into a pure factory function. App.jsx goes from 260 → ~180 lines. Every handler is independently unit-testable.

**Compared to `integration`:** All handlers are inline in the `useWebSocket()` call inside App.jsx (hard to test, hard to scan).

**Action:** Bring `src/hooks/useJarvisEvents.js` into `integration`. Update App.jsx to use it.

---

### NEW-3: Electron restructure + tray extracted

**Files:** `electron/main.js`, `electron/preload.js`, `electron/tray.js`

Key improvements over `integration`'s root-level `main.js`:
- `app.setPath('userData', path.join(app.getPath('home'), '.jarvis-data'))` — fixes "Access is denied" cache error on Windows when `%APPDATA%\jarvis` has permission issues
- `app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')` — suppresses GPU shader cache errors
- `createTray()` extracted to `electron/tray.js` — main.js is 30% shorter
- `package.json` `"main"` points to `electron/main.js` — organized layout
- Build output changed from `src/bundle.js` to `dist/bundle.js` — keeps `src/` clean

**Action:** Adopt the `electron/` directory structure. Note: changing `main` in `package.json` requires `src/index.html` to update its script tag to `../dist/bundle.js`.

---

### NEW-4: CSS split into purpose files

**Files:** `src/styles/base.css`, `src/styles/components.css`, `src/styles/layout.css`, `src/styles/markdown.css`, `src/styles/index.css`

`integration` has a single `src/index.css` (~800+ lines). `new` splits it:

| File | Contents |
|------|---------|
| `base.css` | Reset, scrollbar, animations, CSS variables |
| `layout.css` | App container, sidebars, chat area |
| `components.css` | Buttons, badges, surface card, splash |
| `markdown.css` | `.markdown-content` styles, syntax highlight classes |
| `index.css` | `@import` barrel file |

**Action:** Bring the CSS split from `new`. No behavior change — purely organizational.

---

### NEW-5: `useWebSocket` with exponential backoff reconnect

**File:** `src/hooks/useWebSocket.js`

`new` branch rewrites the hook with:
- `reconnectAttemptsRef` tracking (exponential backoff: 2s → 4s → 8s → capped at 30s)
- `mountedRef` to prevent state updates after component unmount
- Event handler refs updated every render (no stale closure on handlers)
- Centralized inbound event switch using `RECV` constants

`integration`'s hook has a simpler reconnect (flat 3-second retry).

**Action:** Bring `new`'s `useWebSocket.js`. It's backwards-compatible — same `{ sendMessage, connectionStatus }` return shape.

---

### NEW-6: Backend event handler extraction

**File:** `backend/main.py`

`new` extracts the three main event handlers into standalone async functions:
- `_handle_user_query(data, send_event, session_history) → list`
- `_handle_mode_change(data, send_event) → bool`
- `_handle_set_project_path(data, send_event)`

`ws_handler()` becomes a thin dispatcher. Each function is independently testable with `pytest`.

**Integration** keeps all logic inside `ws_handler()`.

**Action:** Apply the extraction to `integration`'s `backend/main.py`.

---

### NEW-7: `_run_tool_loop` and `_execute_tool` extracted

**File:** `backend/ai/claude_client.py`

`new` extracts:
- `_run_tool_loop(messages, task_type, mode, params, send_event)` — the iteration loop
- `_execute_tool(tc, messages, send_event)` — single tool dispatch

`run()` becomes 10 lines. Each part is testable in isolation.

**Integration** keeps everything inside `run()`.

**Action:** Apply extraction to `integration`'s `claude_client.py`.

---

### NEW-8: `validate_providers()` at startup

**File:** `backend/ai/providers.py`

```python
def validate_providers() -> None:
    """Log warnings for any cloud providers with missing API keys."""
    cloud_providers = ("gemini", "groq")
    missing = [name for name in cloud_providers if not _get_providers()[name]["api_key"]]
    for name in missing:
        logger.warning(f"Provider '{name}' has no API key — set {env_var} in .env...")
```

Called from `lifespan()` on startup. Surfaces missing API keys at boot instead of silently falling through the fallback chain at runtime.

**Action:** Copy `validate_providers()` to `integration`'s `providers.py` and call it in `lifespan()`.

---

### NEW-9: Wiki knowledge base

**Files:** `wiki/` directory (12 files)

A structured knowledge base with index, concepts, entities, analyses, setup, and changelog. Follows Obsidian frontmatter format (`type`, `tags`, `confidence`, `links`). Referenced in `wiki/log.md` for session notes.

This is a direct implementation of the Obsidian integration pattern described in `docs/OBSIDIAN_INTEGRATION_GUIDE.md`.

**Action:** Copy the entire `wiki/` directory into `integration`.

---

### NEW-10: Tests reorganized

**Files:** `tests/conftest.py`, `tests/test_prompt.py`, `tests/test_ws_client.py`

Test files moved from project root into a `tests/` directory. `conftest.py` provides shared pytest fixtures.

**Integration** has `test_prompt.py` and `test_ws_client.py` at the root.

**Action:** Move test files to `tests/` directory and add `conftest.py`.

---

## Part 3 — What `integration` Has That `new` Lacks

These are working fixes in `integration` that are absent from `new`.

---

### INT-1: PROJECT_PATH respected by tools

**Files:** `backend/tools/codebase_reader.py`, `backend/tools/git_interface.py`

`integration` fixes both tools to read `os.environ.get("PROJECT_PATH", ".")`:
- `codebase_reader._list_files()` scans the selected project, not JARVIS's own CWD
- `codebase_reader._read_file()` resolves paths relative to PROJECT_PATH
- `git_interface.run()` opens the selected project's git repo

**`new`** still has the original hardcoded `Path(".")` bug.

**Action:** Apply the PROJECT_PATH fixes to `new`'s tool files.

---

### INT-2: Session history injected into system prompt

**File:** `backend/ai/claude_client.py`

`integration` adds:
```python
def _format_session_history() -> str:
    """Read recent sessions from jarvis.json and format for the system prompt."""
    ...

session_summary = _format_session_history()
system = prompts.build_system_prompt(codebase_map=codebase_map, session_history=session_summary)
```

`new` calls `prompts.build_system_prompt(codebase_map=codebase_map)` — `session_history` always defaults to `"No session history loaded."`.

**Action:** Bring `_format_session_history()` into `new`'s `claude_client.py` and pass it to `build_system_prompt`.

---

### INT-3: Markdown→HTML in report sections

**Files:** `backend/tools/report_generator.py`, `backend/templates/report.html`

`integration` completely rewrites the report generator to:
- Process markdown content (`_md_to_html()`, `_inline_md()`) before template rendering
- Format research data as pretty JSON
- New template with table of contents, numbered sections, callout boxes, responsive layout

`new` has the original fallback-only generator with literal `**bold**` text in outputs.

**Action:** Bring `integration`'s `report_generator.py` and `report.html` into `new`.

---

### INT-4: Documentation files

**Files:** `JARVIS_ISSUES_REPORT.md`, `JARVIS_CODEBASE_AUDIT.md`, `docs/JARVIS_ADVANCED_FEATURES_GUIDE.md`, `docs/OBSIDIAN_INTEGRATION_GUIDE.md`

`integration` created four documentation files that don't exist in `new`.

**Action:** Copy all four files into `new`.

---

### INT-5: Bug in `main.py` — duplicate disconnect log line

**File:** `backend/main.py` (new branch, line 245)

`new`'s `main.py` has a duplicated log line introduced during the refactor:
```python
logger.info(f"Client disconnected. Total: {len(connected_clients)}")
logger.info(f"Client disconnected. Total: {len(connected_clients)}")  # ← duplicate
```

This is a minor bug that should be fixed during merge.

---

## Part 4 — Items Unique to Specific Files Not Yet Compared

### `useConversations.js` — missing localStorage

**File:** `src/hooks/useConversations.js` (new branch)

The hook initializes with `useState([])` — conversations are lost on restart. The `integration` branch fixes this with localStorage. Since `useConversations` is the better architecture, the localStorage fix from `integration` should be applied inside the hook (see CONFLICT-1 resolution above).

---

### `new` branch build output path changed

`package.json` in `new` outputs to `dist/bundle.js`. `integration` outputs to `src/bundle.js`. The `src/index.html` `<script>` tag must be updated when adopting `new`'s structure:

```html
<!-- integration uses: -->
<script src="bundle.js"></script>

<!-- new uses (relative to src/index.html): -->
<script src="../dist/bundle.js"></script>
```

---

## Part 5 — Recommended Merge Strategy

The cleanest approach: **start from `new`, apply `integration` fixes on top**.

`new` has the better code structure. `integration` has the working features. The merge brings features into the structure.

### Step-by-step

**Step 1 — Resolve CONFLICT-1 (`App.jsx`)**
Keep `new`'s version. Remove all conflict markers. The `useConversations` hook replaces the inline state.

**Step 2 — Add localStorage to `useConversations.js`**
Change `useState([])` to lazy-init from localStorage. Add `useEffect` to persist on change. This delivers INT-3 (conversation persistence) without touching App.jsx.

**Step 3 — Resolve CONFLICT-2 (`ChatArea.jsx`)**
Keep `new`'s controlled input approach. Add `connectionStatus` prop to the signature. Add `|| connectionStatus !== 'connected'` to both the `<input disabled=` and send `<button disabled=` attributes.

**Step 4 — Apply INT-1 to tool files**
Port the PROJECT_PATH fixes from `integration` to `new`'s `codebase_reader.py` and `git_interface.py`.

**Step 5 — Apply INT-2 to `claude_client.py`**
Add `_format_session_history()` to `new`'s `claude_client.py` and wire it into `run()`.

**Step 6 — Apply INT-3 to report files**
Copy `integration`'s `report_generator.py` and `report.html` into `new`.

**Step 7 — Fix the duplicate log line**
Remove the duplicate `logger.info("Client disconnected...")` from `new`'s `backend/main.py`.

**Step 8 — Copy documentation**
Copy `JARVIS_ISSUES_REPORT.md`, `JARVIS_CODEBASE_AUDIT.md`, `docs/JARVIS_ADVANCED_FEATURES_GUIDE.md`, `docs/OBSIDIAN_INTEGRATION_GUIDE.md` from `integration` to `new`.

**Step 9 — Rebuild**
```bash
npm run build  # outputs to dist/bundle.js per new branch's package.json
```

---

## Full Conflict & Difference Inventory

| # | Type | File | Integration | New | Resolution |
|---|------|------|-------------|-----|------------|
| CONFLICT-1 | Merge conflict | `src/App.jsx` | Inline conversation state + localStorage | `useConversations` hook | Keep `new` hook; add localStorage inside hook |
| CONFLICT-2 | Merge conflict | `src/components/ChatArea.jsx` | Uncontrolled input + `connectionStatus` | Controlled input, no `connectionStatus` | Keep `new` controlled input; add `connectionStatus` prop |
| NEW-1 | Missing in integration | `src/constants/config.js` | Absent | Centralized constants | Copy from `new` |
| NEW-2 | Missing in integration | `src/constants/wsEvents.js` | Absent | Event name registry | Copy from `new` |
| NEW-3 | Missing in integration | `src/hooks/useJarvisEvents.js` | Absent | Extracted event handlers | Copy from `new` |
| NEW-4 | Missing in integration | `src/hooks/useConversations.js` | Absent | Extracted conversation hook | Copy from `new`, add localStorage |
| NEW-5 | Missing in integration | `src/hooks/useWebSocket.js` | Basic reconnect | Exponential backoff + RECV constants | Use `new` version |
| NEW-6 | Missing in integration | `src/styles/` (5 files) | Single `index.css` | Split CSS | Use `new` structure |
| NEW-7 | Missing in integration | `electron/main.js` | `main.js` at root | Organized in `electron/`, userData fix, GPU fix | Adopt `new` |
| NEW-8 | Missing in integration | `electron/preload.js` | `preload.js` at root | In `electron/` | Adopt `new` |
| NEW-9 | Missing in integration | `electron/tray.js` | Inline in main.js | Extracted tray | Use `new` |
| NEW-10 | Missing in integration | `backend/main.py` handlers | Inline in `ws_handler` | Extracted `_handle_*` functions | Use `new` |
| NEW-11 | Missing in integration | `backend/ai/claude_client.py` | `run()` is monolithic | `_run_tool_loop` + `_execute_tool` extracted | Use `new` |
| NEW-12 | Missing in integration | `backend/ai/providers.py` | No startup check | `validate_providers()` | Use `new` |
| NEW-13 | Missing in integration | `wiki/` (12 files) | Absent | Full knowledge base | Copy from `new` |
| NEW-14 | Missing in integration | `tests/conftest.py` | Absent | Pytest fixtures | Copy from `new` |
| NEW-15 | Missing in integration | `tests/` directory | Root-level test files | Organized `tests/` dir | Adopt `new` structure |
| INT-1 | Missing in new | `backend/tools/codebase_reader.py` | PROJECT_PATH fix | Hardcoded `Path(".")` | Apply fix from `integration` |
| INT-2 | Missing in new | `backend/tools/git_interface.py` | PROJECT_PATH fix | Hardcoded CWD git search | Apply fix from `integration` |
| INT-3 | Missing in new | `backend/ai/claude_client.py` | `_format_session_history()` + wired | Missing | Apply from `integration` |
| INT-4 | Missing in new | `backend/tools/report_generator.py` | Full markdown→HTML | Original fallback-only | Copy from `integration` |
| INT-5 | Missing in new | `backend/templates/report.html` | Redesigned with TOC | Original simple template | Copy from `integration` |
| INT-6 | Missing in new | `JARVIS_ISSUES_REPORT.md` | Present | Absent | Copy from `integration` |
| INT-7 | Missing in new | `JARVIS_CODEBASE_AUDIT.md` | Present | Absent | Copy from `integration` |
| INT-8 | Missing in new | `docs/JARVIS_ADVANCED_FEATURES_GUIDE.md` | Present | Absent | Copy from `integration` |
| INT-9 | Missing in new | `docs/OBSIDIAN_INTEGRATION_GUIDE.md` | Present | Absent | Copy from `integration` |
| BUG-1 | Bug in new | `backend/main.py:245` | N/A | Duplicate `logger.info` line | Remove duplicate |
