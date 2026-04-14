---
title: "Groq Llama 3.3 70B"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [ai, model, cloud, groq]
sources: [jarvis.json]
links: [ai-model-routing, jarvis-project-architecture]
confidence: high
---

# Groq Llama 3.3 70B

Groq-hosted Llama 3.3 70B Versatile model, used in Jarvis for summaries, commit messages, and general structured output.

## Role in Jarvis

- **Primary use**: Summaries, commit messages, general QA
- **Why chosen**: Matches Gemini quality for structured short output at lower latency and cost
- **Rejected for**: Error diagnosis (not enough depth for user-facing quality)

## Decision Context

Groq was chosen as the "fast structured output" tier in the [[ai-model-routing]] architecture. It handles the high-throughput, lower-stakes tasks where speed matters more than depth.
