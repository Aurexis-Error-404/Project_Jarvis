# CONFLICTS.md — Cross-Document Discrepancies

**Purpose:** Documents all conflicts found between project docs, with a resolution for each.
**Action required:** Resolve each conflict before implementation begins (ideally at Hour 1–2 contracts meeting).
**Owner:** Integration Lead (Person 4) to arbitrate. AI Lead (Rahul) to sign off on tool schema resolutions.

---

## CONFLICT 1 — WebSocket Port / URL

**Severity:** High — affects every Frontend ↔ Backend connection

| Source | Claims |
|--------|--------|
| `jarvis.json` → `websocket.port` | `8765` |
| Root `CLAUDE.md` | WebSocket: `ws://localhost:8765` · FastAPI: `http://localhost:8000` (two separate servers) |
| `docs/JARVIS BACKEND/BACKEND_PLAN.md` (old) | Same as root CLAUDE.md — separate servers |
| `docs/JARVIS BACKEND/WEBSOCKET_PROTOCOL.md` | `ws://localhost:8000/ws` — WebSocket served through FastAPI on port 8000 (single server) |

**Root cause:** WEBSOCKET_PROTOCOL.md was written assuming FastAPI serves WebSocket at `/ws`. Root CLAUDE.md and jarvis.json assume a separate WebSocket server on port 8765.

**Resolution (recommended):** Use root CLAUDE.md and jarvis.json as authoritative — they are the "locked" docs.
- WebSocket server: `ws://localhost:8765` (standalone `websockets` library, separate from FastAPI)
- FastAPI: `http://localhost:8000` (REST / health endpoints only)
- **Action:** Update `WEBSOCKET_PROTOCOL.md` line 9 from `ws://localhost:8000/ws` to `ws://localhost:8765`

---

## CONFLICT 2 — `read_codebase` Tool Parameters

**Severity:** High — wrong parameters will cause Claude to call the tool with unsupported arguments

| Source | Parameters |
|--------|-----------|
| `prompts/tool_schema.md` (AI Lead's authoritative doc) | `file_path` (relative path from repo root, e.g. `"src/main.py"`) · `lines` (optional range, e.g. `"80-120"`) |
| `docs/JARVIS BACKEND/CLAUDE.md` | `path` (root path to scan) · `depth` (directory depth, default 2) |

**Root cause:** Two different mental models: tool_schema.md treats `read_codebase` as a file reader (read a specific file or list files at `.`). Backend CLAUDE.md treats it as a directory walker with depth control.

**Resolution:** Use `prompts/tool_schema.md` — it is the AI Lead's authoritative schema that Claude actually sees.
- Implement `codebase_reader.py` with parameters: `file_path: str`, `lines: str = None`
- `file_path="."` → list all files (up to MAX_FILES limit)
- `file_path="src/main.py"` → read that file (with optional line range)
- **Action:** Ignore `path` and `depth` parameters from backend CLAUDE.md

---

## CONFLICT 3 — `read_git_history` Tool Parameters

**Severity:** High — same impact as Conflict 2

| Source | Parameters |
|--------|-----------|
| `prompts/tool_schema.md` | `since` (time range: `"24h"`, `"7d"`, `"HEAD~3"`) · `include_diff: bool` · `file_path: str` (optional) |
| `docs/JARVIS BACKEND/CLAUDE.md` | `limit: int` (commit count, default 20) · `include_diff: bool` |

**Root cause:** tool_schema.md uses human-readable time ranges; backend CLAUDE.md uses a raw count.

**Resolution:** Use `prompts/tool_schema.md`.
- Implement `git_interface.py` with parameters: `since: str`, `include_diff: bool = False`, `file_path: str = None`
- Parse `since` as: `"24h"` → last 24 hours, `"7d"` → last 7 days, `"HEAD~3"` → last 3 commits
- **Action:** Ignore `limit` parameter from backend CLAUDE.md

---

## CONFLICT 4 — HTML Report Tool Name

**Severity:** Medium — causes 400 error if Frontend or Claude uses the wrong name

| Source | Tool Name |
|--------|----------|
| `prompts/tool_schema.md` | `generate_html_report` |
| `docs/JARVIS BACKEND/CLAUDE.md` | `generate_report` |

**Resolution:** Use `generate_html_report` from `prompts/tool_schema.md`.
- Register the tool in `TOOL_SCHEMAS` as `"name": "generate_html_report"`
- Route it in `tool_dispatcher.py` to `report_generator.run()`
- **Action:** Update any Frontend or other doc that says `generate_report` to `generate_html_report`

---

## CONFLICT 5 — Memory Tools Architecture

**Severity:** High — two incompatible designs; must pick one before implementation

| Source | Tool Names + Approach |
|--------|----------------------|
| `prompts/tool_schema.md` | `update_project_memory` (writes decisions/questions to jarvis.json) · `read_session_history` (reads session log) · jarvis.json context injected into **system prompt** (no read tool needed) |
| `docs/JARVIS BACKEND/CLAUDE.md` | `read_memory` (reads jarvis.json) · `write_session_summary` (writes session log) |

**Key architectural difference:**
- tool_schema.md: Claude reads project context from the **system prompt** (injected by `prompts.py` at session start). The only write tool is `update_project_memory`. No separate read tool needed.
- backend CLAUDE.md: Claude uses a `read_memory` tool call to fetch jarvis.json. No `update_project_memory` tool.

**Resolution:** Use `prompts/tool_schema.md`'s approach.
- `jarvis.json` is injected into the system prompt by `prompts.py → build_system_prompt()` at session start
- Implement tool `update_project_memory` → writes to jarvis.json via `jarvis_json.update()`
- Implement tool `read_session_history` → reads `session_log` from jarvis.json via `session_log.read()`
- Do NOT implement `read_memory` or `write_session_summary` as tool names
- **Action:** Register `update_project_memory` and `read_session_history` in `TOOL_SCHEMAS`

---

## CONFLICT 6 — jarvis.json Schema

**Severity:** High — backend must read the correct fields or crash

| Source | Schema Fields |
|--------|--------------|
| Actual `jarvis.json` (repo root, the real file) | `project` · `decisions` · `open_questions` · `rejected_approaches` · `ai_config` · `websocket` · `session_log` |
| `docs/JARVIS BACKEND/CLAUDE.md` | `project_name` · `description` · `tech_stack` · `team` · `key_files` · `known_issues` · `goals` |

**Root cause:** Backend CLAUDE.md was written with a placeholder schema that doesn't match the real jarvis.json.

**Resolution:** Use the actual `jarvis.json` at repo root as the authoritative schema.
- `jarvis_json.py` must read fields: `project.name`, `project.stack`, `project.current_focus`, `decisions`, `open_questions`, `rejected_approaches`, `session_log`
- The backend CLAUDE.md schema is **wrong** — do not implement against it
- **Action:** Disregard the schema shown in `docs/JARVIS BACKEND/CLAUDE.md`. Reference `prompts/jarvis_mem.md` for full field documentation.

---

## CONFLICT 7 — Missing Files in BACKEND_PLAN.md

**Severity:** Low — omission only, no contradictory information

| Missing File | Mentioned In | Purpose |
|-------------|-------------|---------|
| `backend/ai/prompts.py` | `docs/JARVIS BACKEND/CLAUDE.md` architecture diagram | Builds the two-block system prompt (static cached + dynamic from jarvis.json). AI Lead owns the content; Backend wires the builder. |
| `backend/tools/tool_dispatcher.py` | `docs/JARVIS BACKEND/CLAUDE.md` architecture notes | Routes `tool_use` blocks from Claude's response to the correct tool implementation. |

**Resolution:** Both files are now added to the file structure in the updated `BACKEND_PLAN.md`.
- `prompts.py` implements `build_system_prompt()` — see `prompts/prompt_struc.md` for the exact template
- `tool_dispatcher.py` implements `dispatch_tool(name, inputs)` — maps tool names to module functions

---

## Summary Table

| # | Conflict | Severity | Resolution |
|---|----------|----------|-----------|
| 1 | WebSocket URL: `8765` vs `8000/ws` | High | Keep `ws://localhost:8765`. Update WEBSOCKET_PROTOCOL.md. |
| 2 | `read_codebase` params: `file_path+lines` vs `path+depth` | High | Use `prompts/tool_schema.md` (`file_path`, `lines`) |
| 3 | `read_git_history` params: `since` vs `limit` | High | Use `prompts/tool_schema.md` (`since`, `include_diff`, `file_path`) |
| 4 | Tool name: `generate_html_report` vs `generate_report` | Medium | Use `generate_html_report` |
| 5 | Memory tools: `update_project_memory` vs `read_memory` | High | Use tool_schema.md approach (inject via system prompt, `update_project_memory` + `read_session_history`) |
| 6 | jarvis.json schema mismatch | High | Use actual `jarvis.json` at repo root |
| 7 | Missing `prompts.py` + `tool_dispatcher.py` in plan | Low | Added to updated BACKEND_PLAN.md |

**Rule:** When in doubt, `prompts/tool_schema.md` and root `CLAUDE.md` + `jarvis.json` win.
