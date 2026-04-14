---
title: "Proactive Context Surfacing"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [ai, architecture, jarvis, core-feature]
sources: [jarvis.json]
links: [zero-search-paradigm, ollama, ai-model-routing, jarvis-project-architecture]
confidence: high
---

# Proactive Context Surfacing

The engine at the heart of Jarvis that detects developer context and automatically surfaces relevant insights without being asked.

## Architecture

```
File/Context Change → Gate (Ollama) → Surface? → Generate Card (Groq) → Display
```

1. **Detection**: File watcher + context monitors detect what the developer is doing
2. **Gate**: [[Ollama]] evaluates whether an insight is worth surfacing (runs 50+/hr)
3. **Generation**: If gate passes, [[Groq Llama]] generates a concise surface card
4. **Display**: Card appears in the Electron overlay via `jarvis_surface` WebSocket event
5. **Cooldown**: TBD — 5 or 10 minutes between surfaces (open question)

## Key Constraint

The gate MUST be local and free. At 50+ evaluations per hour, cloud API costs would be prohibitive. This is why [[Ollama]] is non-negotiable for this component.

## Frontend Handling

- `SurfaceCard.jsx` renders the card
- User can dismiss → sends `surface_dismissed` event back to backend
- Auto-dismiss timer: TBD (8 or 12 seconds)
