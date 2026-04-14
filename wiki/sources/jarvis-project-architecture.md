---
title: "Jarvis Project Architecture"
type: source
created: 2026-04-11
updated: 2026-04-11
tags: [architecture, jarvis, electron, ai, fullstack]
sources: [jarvis.json, main.js, App.jsx, backend/main.py, package.json]
links: [electron, fastapi, gemini-flash, groq-llama, ollama, websocket-contract, zero-search-paradigm, proactive-context-surfacing, ai-model-routing, project-memory]
confidence: high
---

# Jarvis Project Architecture

JARVIS is a desktop application for Windows that proactively surfaces relevant developer context without requiring explicit search. Built as an Electron + React frontend communicating over WebSocket with a Python FastAPI backend, it uses a multi-model AI architecture: Ollama for the local proactive gate, Gemini 2.5 Flash for deep reasoning tasks, and Groq Llama 3.3 70B for fast structured output.

## System Overview

```
┌──────────────────────┐     WebSocket (8765)     ┌──────────────────────┐
│   Electron + React   │ ◄──────────────────────► │  Python FastAPI      │
│   (Desktop UI)       │                           │  (AI Orchestrator)   │
│                      │                           │                      │
│  - Frameless overlay │                           │  - Claude client     │
│  - Ctrl+Space toggle │                           │  - Tool system       │
│  - Chat + surfaces   │                           │  - Codebase reader   │
│  - Mode toggle       │                           │  - Project memory    │
└──────────────────────┘                           └──────┬───────────────┘
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                    ┌──────────┐   ┌──────────┐   ┌──────────┐
                                    │  Ollama   │   │  Gemini  │   │  Groq    │
                                    │  (Local)  │   │  Flash   │   │  Llama   │
                                    │  Gate     │   │  Deep    │   │  Fast    │
                                    └──────────┘   └──────────┘   └──────────┘
```

## Frontend (Electron + React)

- **Entry**: `main.js` — Electron main process. Frameless, transparent window. Hotkey toggle (Ctrl+Space).
- **App**: `src/App.jsx` — Root React component using useReducer for messages, WebSocket hook for backend communication.
- **Components**: SplashScreen, ChatArea, SidebarLeft (conversations, project selector), SidebarRight (reports), SurfaceCard (proactive insights), ModeToggle.
- **Build**: esbuild bundles JSX to `src/bundle.js`.
- **Dependencies**: React 19, marked (markdown), highlight.js (syntax), DOMPurify (sanitization).

## Backend (Python FastAPI)

- **Entry**: `backend/main.py` — FastAPI + WebSocket server.
- **AI client**: `backend/ai/claude_client.py` — orchestrates AI calls.
- **Tools**: `backend/tools/` — codebase reader, etc.
- **Memory**: `backend/memory/` — project memory management.
- **Port**: FastAPI on 8000, WebSocket on 8765.

## AI Model Routing

See [[ai-model-routing]] for full details.

| Task | Model | Why |
|------|-------|-----|
| Proactive gate | Ollama (local) | Runs 50+/hr, must be free |
| Error diagnosis | Gemini 2.5 Flash | User-facing, needs deep reasoning |
| Summaries/commits | Groq Llama 3.3 70B | Fast structured output, low cost |
| Secure mode | Ollama (local) | Zero bytes leave machine |

## WebSocket Protocol

See [[websocket-contract]] for the locked event contract.

## Key Decisions

1. **Structured memory over free-text** — `jarvis.json` schema prevents hallucination. See [[project-memory]].
2. **Local-first** — Default AI_MODE is `local`. Cloud only for testing.
3. **Single instance** — Electron enforces single instance lock.
4. **Pre-rendered hidden window** — Show/hide for <100ms toggle time.

## Open Questions (as of 2026-04-11)

- Proactive gate cooldown: 5 or 10 minutes?
- Max tool iterations: 10 or 15?
- Surface card auto-dismiss: 8 or 12 seconds?
