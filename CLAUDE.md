# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**JARVIS** is a desktop application for Windows that proactively surfaces relevant developer context without requiring explicit search. It uses a "zero-search paradigm" — detecting what developers are working on and automatically surfacing relevant insights.

This is a **48-hour sprint project** with strict feature freeze at Hour 36. See JARVIS.md for team structure, feature goals, and timeline.

## Tech Stack

- **Frontend**: Electron + React
- **Backend**: Python FastAPI + WebSocket server
- **AI Cloud**: Gemini 2.5 Flash (quality-critical) + Groq Llama-3.3-70B (general)
- **AI Local**: Ollama + Qwen 3.5 (for gate and secure mode)
- **Project Memory**: jarvis.json (structured schema at repo root)

## Critical Architecture Decisions

These decisions are locked — do not change without explicit approval from Rahul (AI Lead) or Person 4 (Integration Lead).

### AI Model Routing
- **Proactive gate**: Ollama/Qwen 3.5 (must be free/local — gate runs 50+ times/hour)
- **Error diagnosis & research**: Gemini 2.5 Flash (user-facing quality requires deep reasoning)
- **Summaries, commit messages & general QA**: Groq Llama-3.3-70B (structured output, high throughput)
- **Local secure mode**: Qwen 3.5 via Ollama (zero bytes leave machine — no API calls)

### Project Memory
- **Format**: `jarvis.json` with structured schema (never free-text)
- **Why**: Structured fields prevent hallucination — Claude reads schema, not prose
- **Schema**: See `prompts/jarvis_mem.md` for full field definitions

### Proactive Engine
- **Gate**: Ollama evaluates context → surface or not
- **Surface**: If gate passes, haiku generates concise card
- **Cooldown**: Window TBD (5 min or 10 min — see open_questions in jarvis.json)

## WebSocket Contract (LOCKED)

These event names and directions must not change without updating both frontend and backend simultaneously.

**Frontend → Backend**:
- `user_query` — User submitted query from overlay
- `mode_change` — User toggled secure mode
- `surface_dismissed` — User dismissed surface card

**Backend → Frontend**:
- `jarvis_stream_chunk` — Streaming text chunk from Claude
- `jarvis_surface` — Proactive surface card data
- `jarvis_response` — Non-streamed full response
- `jarvis_mode_ack` — Backend confirmed mode switch
- `jarvis_error` — Backend error — display inline

See `jarvis.json` → `websocket` section for the authoritative list.

## Development Workflow

### Branch Structure
- `main` — stable, integration-tested code. Never push directly.
- `ai` — AI Lead (Rahul) owns all prompt edits. No one else edits `prompts/`.
- `backend` — Backend implementation (Person 2)
- `frontend` — Frontend implementation (Person 3)
- `integration` — Integration testing and merge coordination (Person 4)

**Review Rule**: All merges into `main` require Integration Lead (Person 4) approval.

### Prompt Changes
- **Location**: All prompts live in `prompts/` on the `ai` branch.
- **Rule**: Do not edit prompt files without notifying Rahul first.
- **Gate**: Prompt changes require regression tests passing before merge (see `prompts/prompt_fund.md` for test runner).

### Commits & PRs
- Commits should reference which phase gate they address (Hour 2, Hour 6, etc.).
- PRs to `main` must include evidence of testing against relevant gate.

## Startup Order (CRITICAL)

Always start services in this order:

```bash
# 1. Start Ollama (local AI gate) — runs on Rahul's machine RTX 4090
ollama serve

# 2. Start backend WebSocket + FastAPI server
cd backend
python main.py
# Runs on: http://localhost:8000 (FastAPI) + ws://localhost:8765 (WebSocket)

# 3. Start frontend Electron app
cd frontend
npm start
# Communicates with backend via WebSocket at ws://localhost:8765
```

**Ports are locked** — never change:
- WebSocket: `ws://localhost:8765`
- FastAPI: `http://localhost:8000`
- Ollama: `http://localhost:11434`

## Configuration

### Environment Variables
- `GEMINI_API_KEY`: Required for Claude API calls (error diagnosis, summaries)
- `AI_MODE`: Set to `local` by default (Ollama during development). Switch to `cloud` only for testing research report pipeline.
- See `.env.example` for template.

### AI Configuration (from jarvis.json)
```json
{
  "ai_config": {
    "mode": "local",
    "cloud_model": "gemini-2.5-flash",
    "haiku_model": "llama-3.3-70b-versatile (Groq)",
    "local_model": "ollama/qwen3.5:cloud",
    "max_tool_iterations": 10,
    "system_prompt_version": "v1"
  }
}
```

These values are locked. Changing them requires approval.

## Prompt Files Reference

**Don't memorize these — refer to them when implementing features.**

| File | Purpose |
|------|---------|
| `prompts/tool_schema.md` | All 6 tool definitions (gates, surfaces, etc.) |
| `prompts/prompts.md` | Gate, surface, error diagnosis, research report prompts |
| `prompts/prompt_struc.md` | System prompt v1 template |
| `prompts/model.md` | Model routing logic and decision flow |
| `prompts/prompt_caching.md` | Prompt caching setup and verification |
| `prompts/prompt_fund.md` | Regression test runner for prompt changes |
| `prompts/jarvis_mem.md` | jarvis.json schema documentation |
| `prompts/bonus.md` | Advanced features (post-48hr scope) |

## Phase 1 Feature Checklist (48 Hours)

These are the only features targeted for the sprint:

- [ ] Hotkey overlay (Ctrl+Space)
- [ ] Proactive context surface (file watcher + Ollama gate + haiku surface)
- [ ] Codebase awareness (reads /src at session start)
- [ ] Project memory (jarvis.json — structured, never hallucinated)
- [ ] Error diagnosis with codebase context
- [ ] Local-first secure mode (Ollama toggle)

**Feature freeze at Hour 36** — no new features after this point.

## Cost Controls

- **Hard cap**: $20 API spend
- **Default AI_MODE**: `local` (Ollama during development)
- **Proactive gate**: Always uses Ollama, never Claude API
- **Only switch to `cloud=true`** for testing research report pipeline
- Monitor spending via `jarvis.json` session_log

## Key Milestones (Gates)

These are hard deadlines with owners:

| Time | Gate | Owner | What it means |
|------|------|-------|---------------|
| Hour 2 | Contracts locked | Rahul | WebSocket events + tool schemas agreed |
| Hour 6 | "Hello Jarvis" e2e | Person 4 | Full flow working: query → response |
| Hour 18 | Proactive engine 5/5 | Rahul + Person 4 | Gate + surface reliable |
| Hour 36 | Feature freeze | Everyone | No new features allowed |
| Hour 47 | Demo ×5 | Person 5 | Demo runs 5 times, timed to 3 minutes |

## What NOT to Change Without Approval

- WebSocket event names or directions (see WebSocket Contract above)
- Prompt files without Rahul's sign-off
- Port numbers (8000, 8765, 11434)
- AI model assignments (gate=Ollama, errors=Sonnet, etc.)
- jarvis.json schema structure
- Branch naming or review rules

## Common Workflow Tasks

### Setting up development
1. Clone the repository
2. Copy `.env.example` to `.env` and add `GEMINI_API_KEY`
3. Pull the relevant branch (e.g., `ai`, `backend`, `frontend`)
4. Install dependencies in `backend/` and `frontend/` as they're added
5. Follow startup order (Ollama → backend → frontend)

### Testing prompt changes
```bash
# From root
python prompts/prompt_fund.md  # Runs regression tests
# Must pass before merging prompt changes to main
```

### Debugging WebSocket communication
- Frontend logs: Check Electron DevTools console (Ctrl+Shift+I in app)
- Backend logs: Check FastAPI/WebSocket server output (where `python main.py` runs)
- Verify ports: `netstat -an | grep 8765` (WebSocket), `netstat -an | grep 8000` (FastAPI)

## Key Constraints

- **Time**: 48-hour sprint with Hour 36 feature freeze
- **Budget**: $20 max API spend
- **Resources**: RTX 4090 (Ollama), RTX 4050 (backend), RTX 3050 (frontend)
- **Integration**: All code must merge through Person 4 to `main`
- **Prompts**: Rahul owns all prompt files — no edits without notification

## Open Questions

See `jarvis.json` → `open_questions` for TBD design decisions:
- Proactive gate cooldown window — 5 or 10 minutes?
- Max tool iterations before hard stop — 10 or 15?
- Surface card auto-dismiss timer — 8 or 12 seconds?

**These should be decided at Hour 2** when contracts are locked. Until then, ask Rahul.
