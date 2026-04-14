---
title: "Jarvis Architecture Review"
type: analysis
created: 2026-04-11
updated: 2026-04-11
tags: [architecture, review, jarvis]
sources: [jarvis.json, main.js, App.jsx, backend/main.py, package.json]
links: [jarvis-project-architecture, ai-model-routing, zero-search-paradigm, proactive-context-surfacing, project-memory, electron, fastapi]
confidence: high
---

# Jarvis Architecture Review — 2026-04-11

Initial architecture review conducted during wiki setup. This is a system map of the entire Project Jarvis codebase as it exists today.

## System Health

**Overall**: The architecture is sound. Clear separation between frontend (Electron/React), backend (Python/FastAPI), and AI layers. Good design decisions documented in jarvis.json.

## Strengths

1. **Multi-model routing is smart** — Using the right model for each task tier is cost-effective and quality-appropriate. See [[ai-model-routing]].
2. **Structured memory prevents drift** — jarvis.json schema is a better approach than free-text. See [[project-memory]].
3. **WebSocket contract is locked** — Having a frozen protocol between frontend and backend prevents integration bugs. See [[websocket-contract]].
4. **Local-first default** — Running Ollama locally keeps costs down during development.
5. **Pre-rendered hidden window** — Smart UX pattern for fast toggle (<100ms).

## Areas to Watch

1. **Open questions are stale** — Cooldown, max iterations, and auto-dismiss values were supposed to be decided at Hour 2. They're still open. These need resolution.
2. **Single-machine dependency** — Ollama running on Rama's RTX 4090 is a single point of failure for the team.
3. **No test infrastructure visible** — No test files in the frontend, only `test_prompt.py` and `test_ws_client.py` at root level.
4. **Backend structure is deep** — `backend/ai/`, `backend/tools/`, `backend/memory/`, `backend/context/`, `backend/templates/` — worth mapping in more detail in a future ingest.

## Suggested Next Ingests

- Deep-dive into `backend/ai/claude_client.py` — the AI orchestration core
- Map the `prompts/` directory — all prompt templates
- Ingest any design documents or team communication about the project
- Review the `backend/tools/` directory for the full tool system

## File Map

```
Project_Jarvis/
├── main.js                    # Electron main process
├── preload.js                 # Electron preload (IPC bridge)
├── src/
│   ├── App.jsx                # Root React component
│   ├── index.jsx              # React entry
│   ├── index.html             # HTML shell
│   ├── index.css              # Global styles
│   ├── components/            # React components (7 files)
│   ├── hooks/                 # Custom hooks (WebSocket, conversations, events)
│   ├── reducers/              # Message state reducer
│   └── utils/                 # Markdown rendering
├── backend/
│   ├── main.py                # FastAPI + WebSocket server
│   ├── ai/                    # AI client
│   ├── tools/                 # Tool system
│   ├── memory/                # Project memory
│   ├── context/               # Context management
│   └── templates/             # Prompt templates
├── prompts/                   # AI prompt files (8 files)
├── jarvis.json                # Structured project memory
└── wiki/                      # This knowledge base
```
