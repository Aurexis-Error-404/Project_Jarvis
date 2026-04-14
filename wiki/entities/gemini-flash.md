---
title: "Gemini 2.5 Flash"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [ai, model, cloud, google]
sources: [jarvis.json]
links: [ai-model-routing, jarvis-project-architecture]
confidence: high
---

# Gemini 2.5 Flash

Google's Gemini 2.5 Flash model, used in Jarvis for quality-critical tasks that require deep reasoning — primarily error diagnosis and research reports.

## Role in Jarvis

- **Primary use**: Error diagnosis with codebase context
- **Why chosen over Groq**: User-facing quality requires deeper reasoning capability
- **Requires**: `GEMINI_API_KEY` environment variable
- **Cost**: Part of the $20 API spend hard cap

## Decision Context

Gemini Flash was chosen over Llama 3.3 70B (Groq) for error diagnosis because user-facing quality demands deep reasoning. Groq handles the structured, lower-stakes tasks instead. See [[ai-model-routing]].
