---
title: "Electron"
type: entity
created: 2026-04-11
updated: 2026-04-11
tags: [frontend, desktop, runtime]
sources: [main.js, package.json]
links: [jarvis-project-architecture, websocket-contract]
confidence: high
---

# Electron

Electron is the desktop runtime powering the Jarvis frontend. It enables a frameless, transparent, always-on-top overlay window that toggles with Ctrl+Space.

## Role in Jarvis

- Runs `main.js` as the main process
- Creates a frameless BrowserWindow (1280x800 default, maximized on show)
- Registers global hotkey (Ctrl+Space, fallback Ctrl+Shift+Space)
- System tray icon with Open/Quit menu
- IPC for native directory picker (`select-project-dir`)
- Context isolation enabled, node integration disabled (security)
- Single instance enforced via `requestSingleInstanceLock()`

## Version

Electron 41.2.0 (as of package.json)

## Key Design Choices

- **Pre-rendered hidden window**: Window is created at startup but hidden. Toggle is pure show/hide for <100ms response.
- **No alwaysOnTop**: Set to `false` — acts as a normal window, not a persistent overlay.
- **Sandbox disabled**: Preload script needs Node access for `require('path')` and shell operations.
