---
title: "AI Model Routing"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [ai, architecture, multi-model]
sources: [jarvis.json]
links: [ollama, gemini-flash, groq-llama, proactive-context-surfacing, jarvis-project-architecture]
confidence: high
---

# AI Model Routing

Jarvis uses a multi-model architecture where different AI tasks route to different models based on quality requirements, cost, and latency constraints.

## Routing Table

| Task | Model | Tier | Rationale |
|------|-------|------|-----------|
| Proactive gate | Ollama / Qwen 3.5 | Local, free | Runs 50+/hr — must have zero cost |
| Error diagnosis | Gemini 2.5 Flash | Cloud, quality | User-facing — needs deep reasoning |
| Research reports | Gemini 2.5 Flash | Cloud, quality | Complex synthesis |
| Summaries | Groq Llama 3.3 70B | Cloud, fast | Structured output, low latency |
| Commit messages | Groq Llama 3.3 70B | Cloud, fast | Short structured output |
| General QA | Groq Llama 3.3 70B | Cloud, fast | High throughput |
| Secure mode (all) | Ollama / Qwen 3.5 | Local, private | Zero bytes leave machine |

## Design Principles

1. **Cost-tiered**: Free local for high-frequency, paid cloud for quality-critical
2. **Quality-matched**: Deep reasoning where users see output, fast output for internal tasks
3. **Privacy-aware**: Secure mode routes everything local — no exceptions
4. **Budget-capped**: $20 hard cap on API spend across the project

## Rejected Approaches

- Claude API for proactive gate (too expensive at 50+/hr)
- Sonnet for all tasks (overkill for structured output, too expensive)
- Single model for everything (can't satisfy all constraints simultaneously)
