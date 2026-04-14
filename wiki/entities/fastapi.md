---
title: "FastAPI"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [backend, python, api]
sources: [backend/main.py]
links: [jarvis-project-architecture, websocket-contract]
confidence: high
---

# FastAPI

Python web framework running the Jarvis backend. Serves both the REST API (port 8000) and manages the WebSocket server (port 8765).

## Role in Jarvis

- Entry point: `backend/main.py`
- Hosts the AI orchestration layer
- Manages WebSocket connections to the Electron frontend
- Broadcasts events to all connected clients
- Loads codebase map on first client connection (codebase awareness)
- Tracks current AI mode (local/cloud)

## Architecture

```
backend/
├── main.py          # FastAPI + WebSocket entry
├── ai/              # AI client (claude_client.py)
├── context/         # Context management
├── tools/           # Tool system (codebase reader, etc.)
├── memory/          # Project memory
├── templates/       # Prompt templates
└── logs/            # Error logs
```
