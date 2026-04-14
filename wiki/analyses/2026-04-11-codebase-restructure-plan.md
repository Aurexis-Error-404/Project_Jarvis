---
title: "Codebase Restructure Plan"
type: analysis
created: 2026-04-11
updated: 2026-04-11
tags: [architecture, refactor, organization]
sources: [main.js, preload.js, App.jsx, package.json]
links: [jarvis-project-architecture, electron, fastapi]
confidence: high
---

# Codebase Restructure Plan

Analysis of current vs ideal directory structure for Project Jarvis.

## Problems Identified

1. **Electron files scattered at root** — main.js, preload.js mixed with config files
2. **No clear electron/ directory** — main process, preload, and window management not grouped
3. **829-line monolith CSS** — single index.css for the entire app
4. **Stray files at root** — 2026-04-11.md (empty), Untitled.base, test files
5. **prompts/ directory is empty** — referenced in old CLAUDE.md but contains nothing
6. **docs/ has only HTML exports** — no markdown docs
7. **No separation between Electron config and React app**
8. **reports/ contains generated HTML** — belongs in a gitignored output directory
9. **scripts/ has only 2 utility files** — fine but undersells the need for dev tooling

## Current vs Ideal Structure

See the main response for the full proposed layout.
