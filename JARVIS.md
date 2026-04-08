# JARVIS — Proactive Developer Intelligence Layer

## What it is
A desktop app for Windows that proactively surfaces relevant developer context before you ask.
Zero-Search paradigm — Jarvis detects what you're working on and surfaces insights automatically.

## Team
| Role | Person | Branch | Machine |
|---|---|---|---|
| AI Lead | Rahul | `ai` | RTX 4090 |
| Backend Implementor | Person 2 | `backend` | RTX 4050 |
| Frontend Implementor | Person 3 | `frontend` | RTX 3050 |
| Integration Lead | Person 4 | `integration` | RTX 4050 |
| Research + Docs | Person 5 | `main` | RTX 2050 |

## Stack
- Frontend: Electron + React
- Backend: Python FastAPI + WebSocket server
- AI Cloud: Claude API (claude-sonnet-4-20250514, claude-haiku-4-5-20251001)
- AI Local: Ollama + CodeLlama (runs on Rahul's RTX 4090)
- Project Memory: jarvis.json (repo root)

## Ports (never change these)
| Service | Address |
|---|---|
| WebSocket | ws://localhost:8765 |
| FastAPI | http://localhost:8000 |
| Ollama | http://localhost:11434 |

## Run Order (always this sequence)
```bash
# 1. Start Ollama (Rahul's machine)
ollama serve

# 2. Start backend
cd backend
python main.py

# 3. Start frontend
cd frontend
npm start
```

## WebSocket Events (LOCKED — do not change names)
| Event | Direction | Description |
|---|---|---|
| `user_query` | Frontend → Backend | User submitted query from overlay |
| `mode_change` | Frontend → Backend | User toggled secure mode |
| `surface_dismissed` | Frontend → Backend | User dismissed surface card |
| `jarvis_stream_chunk` | Backend → Frontend | Streaming text chunk from Claude |
| `jarvis_surface` | Backend → Frontend | Proactive surface card data |
| `jarvis_response` | Backend → Frontend | Non-streamed full response |
| `jarvis_mode_ack` | Backend → Frontend | Backend confirmed mode switch |
| `jarvis_error` | Backend → Frontend | Backend error — display inline |

## Phase 1 Features (48-hour build)
- Hotkey overlay (Ctrl+Space)
- Proactive context surface (file watcher + Ollama gate + haiku surface)
- Codebase awareness (reads /src at session start)
- Project memory (jarvis.json — structured, never hallucinated)
- Error diagnosis with codebase context
- Local-first secure mode (Ollama toggle)

## Branch Rules
- Never push directly to `main`
- Integration Lead (Person 4) reviews all merges into `main`
- AI Lead (Rahul) owns all prompt files — no one else edits prompts/
- Prompt changes require regression tests passing before merge
- Feature freeze at Hour 36 — no new features after this

## Key Gates
| Time | Gate | Owner |
|---|---|---|
| Hour 2 | Contracts locked — WebSocket events + tool schemas agreed | Rahul |
| Hour 6 | "Hello Jarvis" end-to-end working | Person 4 |
| Hour 18 | Proactive engine 5/5 reliable | Rahul + Person 4 |
| Hour 36 | Feature freeze | Everyone |
| Hour 47 | Demo run ×5, timed to 3 minutes | Person 5 |

## Cost Controls
- Hard cap: $20 API spend
- AI_MODE=local by default in .env (Ollama during development)
- Proactive gate always uses Ollama — never Claude API
- Only switch to cloud=true for testing research report pipeline

## Prompts Location
All prompt files live in `prompts/` on the `ai` branch.
Do not edit these files without telling Rahul first.

| File | What it contains |
|---|---|
| `prompts/tool_schema.md` | All 6 tool definitions |
| `prompts/prompts.md` | Gate, surface, error diagnosis, research report prompts |
| `prompts/prompt_struc.md` | System prompt v1 template |
| `prompts/model.md` | Model routing logic |
| `prompts/prompt_caching.md` | Cache setup and verification |
| `prompts/prompt_fund.md` | Regression test runner |
| `prompts/jarvis_memory.md` | jarvis.json schema documentation |