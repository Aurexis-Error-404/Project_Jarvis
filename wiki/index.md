---
title: "Wiki Index"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [meta, index]
sources: []
links: []
confidence: high
---

# Wiki Index

Master catalog of all wiki pages. Claude reads this first when answering queries.

---

## Sources

- [[jarvis-project-architecture]] — Full architecture breakdown of the Jarvis desktop assistant (sources: jarvis.json, CLAUDE.md, main.js, App.jsx, backend/main.py)

## Entities

- [[electron]] — Desktop runtime powering Jarvis frontend
- [[fastapi]] — Python web framework running the Jarvis backend
- [[gemini-flash]] — Google's Gemini 2.5 Flash model used for error diagnosis and research
- [[groq-llama]] — Groq-hosted Llama 3.3 70B used for summaries and structured output
- [[ollama]] — Local AI inference server running the proactive gate
- [[websocket-contract]] — Locked protocol between Jarvis frontend and backend

## Concepts

- [[zero-search-paradigm]] — Core design philosophy of Jarvis: no explicit search needed
- [[proactive-context-surfacing]] — The engine that detects developer context and surfaces insights automatically
- [[ai-model-routing]] — Multi-model architecture: local gate, cloud reasoning, fast structured output
- [[project-memory]] — jarvis.json structured schema preventing hallucination

## Analyses

- [[2026-04-11-jarvis-architecture-review]] — Initial architecture review and system map of Project Jarvis
- [[2026-04-11-codebase-restructure-plan]] — Current vs ideal directory structure, problems identified
