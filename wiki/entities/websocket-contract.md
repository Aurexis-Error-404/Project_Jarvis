---
title: "WebSocket Contract"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [protocol, architecture, locked]
sources: [jarvis.json]
links: [jarvis-project-architecture, electron, fastapi]
confidence: high
---

# WebSocket Contract

The locked communication protocol between the Jarvis Electron frontend and the Python FastAPI backend. Port 8765. Changes require updating both sides simultaneously.

## Frontend -> Backend

| Event | Purpose |
|-------|---------|
| `user_query` | User submitted query from overlay |
| `mode_change` | User toggled secure mode |
| `surface_dismissed` | User dismissed surface card |

## Backend -> Frontend

| Event | Purpose |
|-------|---------|
| `jarvis_stream_chunk` | Streaming text chunk from AI |
| `jarvis_surface` | Proactive surface card data |
| `jarvis_response` | Non-streamed full response |
| `jarvis_mode_ack` | Backend confirmed mode switch |
| `jarvis_error` | Backend error — display inline |

## Status

**LOCKED** — These event names and directions must not change without explicit approval and simultaneous frontend/backend update.
