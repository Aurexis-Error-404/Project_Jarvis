# CONTRACTS.md — JARVIS Role Boundary Contracts

> **This document prevents merge conflicts, scope creep, and last-minute surprises.**
> Every role must read this. Every interface crossing requires the owning role's acknowledgment.

---

## The 5 Roles

| Role | Person | Color | Owns |
|---|---|---|---|
| AI Lead | Rahul | 🟡 Gold | Prompts, tool schemas, jarvis.json content, AI mode decisions |
| Backend Implementor | Person 2 | 🟢 Teal | `backend/` directory, all Python, WebSocket server |
| Frontend Implementor | Person 3 | 🔵 Blue | `frontend/` directory, Electron, React components |
| Integration Lead | Person 4 | 🔴 Red | GitHub repo, branch merges, `.env.example`, demo machine |
| Research + Docs | Person 5 | 🟣 Purple | `jarvis.json` values, Jinja2 templates, demo script |

---

## Interface Contracts

### Contract 1: AI Lead ↔ Backend
**What AI Lead gives Backend:**
- Complete tool schemas (JSON, all fields) — by Hour 2
- WebSocket event structure — by Hour 2
- System prompt content for `prompts.py` — by Hour 6
- Sample outputs showing expected tool responses — by Hour 9

**What Backend gives AI Lead:**
- Confirmation that all 6 tools are implemented and callable — by Hour 11
- Raw output from `codebase_reader` and `git_interface` so AI Lead can write good prompts — by Hour 9
- Notification any time a tool schema needs to change (ask first, never unilaterally change)

**Conflict rule:** If a tool schema needs to change, AI Lead makes the decision. Backend implements. No exceptions.

---

### Contract 2: Backend ↔ Frontend
**What Backend gives Frontend:**
- WebSocket endpoint: `ws://localhost:8000/ws`
- Sends exactly these events, exactly these payloads:

```
jarvis_reply        → { event, text, timestamp }
tool_call_status    → { event, tool, status: "start"|"done", result? }
status_update       → { event, message }
report_generated    → { event, path, html }
context_surface     → { event, file, reason }
error               → { event, message, recoverable }
```

- Backend sends events in this order: `status_update` → `tool_call_status (start)` → `tool_call_status (done)` → `jarvis_reply`

**What Frontend gives Backend:**
- WebSocket messages in exactly this format:
  ```json
  { "query": "string", "mode": "local|cloud" }
  ```
- No other fields. If new fields are needed, update this contract first.

**Conflict rule:** Backend owns event names and payloads. Frontend owns how they're rendered. If Frontend needs a new event, raise it with AI Lead + Backend to agree on name and payload before implementation.

---

### Contract 3: Backend ↔ Research+Docs
**What Docs gives Backend:**
- `jarvis.json` at repo root by Hour 2 — Backend will read this, never write it
- Jinja2 report template at `backend/templates/report.html` by Hour 20
- Template variable list so Backend knows what to pass to `report_generator.py`

**What Backend gives Docs:**
- `report_generator.py` accepts: `{ title: str, sections: list[dict], output_path: str }`
- Sends `report_generated` event with `{ path, html }` after generating
- Backend will not modify templates — that's Docs' territory

**Conflict rule:** Backend's `report_generator.py` calls the template but does not own it. If a template variable is missing, Docs adds it. If a new section type is needed, Backend and Docs agree on the dict structure.

---

### Contract 4: All Roles ↔ Integration Lead
**Integration Lead's authority:**
- Controls `main` branch — all merges go through Integration Lead
- Controls `.env.example` — any new env variable must be added here
- Controls demo machine setup
- Runs pipeline tests at Hour 6, Hour 18, Hour 28, Hour 36

**Branch naming:**
```
backend/[feature-name]
frontend/[feature-name]
ai/[feature-name]
docs/[feature-name]
```

**PR rules:**
- PRs must describe what was changed and what to test
- Never force-push to `main`
- Integration Lead resolves cross-directory conflicts. Within-directory conflicts are resolved by the directory owner.

---

### Contract 5: AI Mode Decision
**This is entirely AI Lead's call.**
- Default is `AI_MODE=local` (Ollama)
- Switch to `AI_MODE=cloud` only if AI Lead decides
- During demo: AI Lead decides which mode is shown first
- Backend implements the router; AI Lead tunes the threshold

---

## Locked Decisions (No Changes Without All-Team Agreement)

These were decided at Hour 0–2 and cannot be changed without a 5-person sync:

1. **WebSocket event names** — listed above. Changing a name breaks Frontend + Backend simultaneously.
2. **Tool names** — listed in CLAUDE.md. Changing a name breaks the Claude loop and all prompt references.
3. **jarvis.json field names** — AI Lead owns. Backend reads. Docs fills. Nobody renames fields.
4. **Port 8000** — Backend serves on `localhost:8000`. Frontend connects to `localhost:8000`. Integration Lead configures demo machine for port 8000.

---

## Escalation Protocol

If a conflict arises:
1. Stop. Do not merge. Do not push to main.
2. Post in group chat: "Conflict on [file/feature] — need sync"
3. Wait for Integration Lead to call a 10-minute sync
4. The role that **owns** the disputed area makes the final call
5. Document the decision in this file

---

## The One Rule

> **Never change something you don't own without asking the owner first.**

If you're unsure who owns it — ask Integration Lead.
