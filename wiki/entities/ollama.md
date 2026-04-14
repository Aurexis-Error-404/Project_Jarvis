---
title: "Ollama"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [ai, model, local, inference]
sources: [jarvis.json]
links: [ai-model-routing, proactive-context-surfacing, jarvis-project-architecture]
confidence: high
---

# Ollama

Local AI inference server used in Jarvis for the proactive gate and secure mode. Runs on Rama's RTX 4090.

## Role in Jarvis

- **Proactive gate**: Evaluates context 50+ times/hour to decide whether to surface insights. Must be free and local — no API cost.
- **Secure mode**: When toggled, ALL AI processing goes through Ollama. Zero bytes leave the machine.
- **Model**: Qwen 3.5 (`ollama/qwen3.5:cloud` in config)
- **Port**: `http://localhost:11434`

## Why Local

The proactive gate runs at extremely high frequency. Using a cloud API would be cost-prohibitive and add latency. Ollama makes the gate essentially free.

Secure mode is a privacy guarantee — no data transmitted externally. This is a non-negotiable design constraint.
