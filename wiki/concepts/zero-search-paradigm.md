---
title: "Zero-Search Paradigm"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [architecture, philosophy, jarvis]
sources: [jarvis.json]
links: [proactive-context-surfacing, jarvis-project-architecture, ai-model-routing]
confidence: high
---

# Zero-Search Paradigm

The core design philosophy of Project Jarvis: developers should never need to explicitly search for context. The system detects what you're working on and automatically surfaces relevant insights.

## How It Works

Instead of the developer querying for information, Jarvis:
1. **Monitors** the developer's active context (file changes, errors, patterns)
2. **Evaluates** via the [[proactive-context-surfacing]] engine whether an insight is worth surfacing
3. **Generates** a concise surface card with the relevant information
4. **Presents** it non-intrusively — the developer sees it only when it's useful

## Why This Matters

Traditional developer tools require context switching: stop coding, formulate a query, read results, switch back. The zero-search paradigm eliminates that friction. The AI does the searching; the developer stays in flow.

## Relationship to LLM Wiki Pattern

This wiki itself follows a related philosophy — knowledge should be pre-compiled and maintained, not re-derived on every query. The wiki is the "zero-search" approach applied to knowledge management.
