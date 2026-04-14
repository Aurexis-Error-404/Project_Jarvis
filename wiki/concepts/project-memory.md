---
title: "Project Memory (jarvis.json)"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [architecture, memory, data]
sources: [jarvis.json]
links: [jarvis-project-architecture, ai-model-routing]
confidence: high
---

# Project Memory (jarvis.json)

Jarvis uses a structured JSON schema (`jarvis.json`) as its project memory. This was a deliberate choice over free-text notes to prevent AI hallucination.

## Why Structured Over Free-Text

- Structured fields force the AI to read schema, not prose
- Prevents hallucination — fields are typed and constrained
- Machine-readable — easy to query and validate
- Version-controllable — diffs are meaningful

## Schema Structure

```json
{
  "project": { "name", "stack", "current_focus", "repo_root" },
  "decisions": [{ "what", "chose", "rejected", "reason" }],
  "open_questions": ["..."],
  "rejected_approaches": ["..."],
  "ai_config": { "mode", "cloud_model", "fallback_model", "local_model", ... },
  "websocket": { "port", "events_send", "events_receive" },
  "session_log": [{ "timestamp", "messages", "mode" }]
}
```

## Key Design

- **Decisions array**: Records what was chosen, what was rejected, AND why. This prevents relitigating settled decisions.
- **Open questions**: Explicit list of unresolved design decisions.
- **Session log**: Tracks usage patterns over time.

## Relationship to This Wiki

This wiki is a higher-level knowledge system that WRAPS the jarvis.json data. The wiki synthesizes, cross-references, and adds context. jarvis.json is a raw source; the wiki is the compiled knowledge.
