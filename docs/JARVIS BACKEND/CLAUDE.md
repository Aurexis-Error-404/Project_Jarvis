# CLAUDE.md — JARVIS Project Context

> This file is read by AI assistants (Claude, Copilot, etc.) to understand the project.
> Do NOT edit field names. AI Lead owns this file's content. Backend commits structure only.

## Project Overview

**JARVIS** is a local-first AI assistant for developers. It monitors your codebase, answers questions about your project using real file context, and generates structured reports — all without sending code to the cloud by default.

**Stack:** Python FastAPI backend · Electron + React frontend · Claude API (cloud) · Ollama (local/secure mode)

---

## Architecture — How It Works

```
Electron UI  ──WebSocket──►  FastAPI (main.py)
                                    │
                         ┌──────────▼──────────┐
                         │   AI Router          │
                         │  (router.py)         │
                         └──────────┬──────────┘
                          local ◄───┤───► cloud
                       Ollama gate  │   Claude API
                                    │
                         ┌──────────▼──────────┐
                         │   Tool Use Loop      │
                         │  (claude_client.py)  │
                         └──────────┬──────────┘
                    ┌───────────────┼───────────────┐
               codebase_reader  git_interface   web_research
               report_generator  memory tools  file_watcher
```

---

## File Structure

```
backend/
├── main.py                    # FastAPI entry point — start here
├── ai/
│   ├── claude_client.py       # Tool-use loop — most critical file
│   ├── ollama_client.py       # Local model calls + gate prompt
│   ├── router.py              # Decides which model handles request
│   └── prompts.py             # System prompt builder (AI Lead owns content)
├── tools/
│   ├── codebase_reader.py     # Reads project files via pathlib
│   ├── git_interface.py       # Reads git log/diff via gitpython
│   ├── web_research.py        # Playwright-based web scraper
│   └── report_generator.py   # Jinja2 HTML report writer
├── memory/
│   ├── jarvis_json.py         # Read/write jarvis.json
│   └── session_log.py         # Session summaries
└── context/
    └── file_watcher.py        # Proactive file change engine

frontend/
├── src/
│   ├── App.jsx                # Main React component
│   ├── components/            # UI components
│   └── ws/                    # WebSocket client logic
└── main.js                    # Electron entry point

jarvis.json                    # Project-specific context (AI Lead owns)
.env                           # Local secrets — never commit
.env.example                   # Committed template
```

---

## WebSocket Protocol (Locked — Do Not Change Without AI Lead Sign-off)

### Client → Server

```json
{ "query": "string", "mode": "local|cloud" }
```

### Server → Client Events

| Event | Payload | When |
|---|---|---|
| `jarvis_reply` | `{ text, timestamp }` | Final AI response |
| `tool_call_status` | `{ tool, status: "start\|done", result? }` | Tool execution updates |
| `status_update` | `{ message }` | Loading text (e.g. "Thinking...") |
| `report_generated` | `{ path, html }` | After report_generator runs |
| `context_surface` | `{ file, reason }` | File watcher surfaces a change |
| `error` | `{ message, recoverable }` | Any failure |

---

## Tool Definitions (All 6 — Backend Implements, AI Lead Owns Schemas)

### 1. `read_codebase`
```json
{
  "name": "read_codebase",
  "description": "Read the project file tree and contents of relevant files.",
  "input_schema": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Root path to scan. Default: PROJECT_PATH from env." },
      "depth": { "type": "integer", "description": "Directory depth. Default: 2." }
    }
  }
}
```

### 2. `read_git_history`
```json
{
  "name": "read_git_history",
  "description": "Read recent git commits, diffs, and branch info.",
  "input_schema": {
    "type": "object",
    "properties": {
      "limit": { "type": "integer", "description": "Number of commits. Default: 20." },
      "include_diff": { "type": "boolean", "description": "Include file diffs. Default: false." }
    }
  }
}
```

### 3. `web_research`
```json
{
  "name": "web_research",
  "description": "Scrape a URL and return clean text content.",
  "input_schema": {
    "type": "object",
    "required": ["url"],
    "properties": {
      "url": { "type": "string" },
      "selector": { "type": "string", "description": "CSS selector to target. Optional." }
    }
  }
}
```

### 4. `generate_report`
```json
{
  "name": "generate_report",
  "description": "Write a structured HTML report using Jinja2 templates.",
  "input_schema": {
    "type": "object",
    "required": ["title", "sections"],
    "properties": {
      "title": { "type": "string" },
      "sections": { "type": "array", "items": { "type": "object" } },
      "output_path": { "type": "string" }
    }
  }
}
```

### 5. `read_memory`
```json
{
  "name": "read_memory",
  "description": "Read jarvis.json and recent session summaries.",
  "input_schema": { "type": "object", "properties": {} }
}
```

### 6. `write_session_summary`
```json
{
  "name": "write_session_summary",
  "description": "Append a summary of this session to session_log.",
  "input_schema": {
    "type": "object",
    "required": ["summary"],
    "properties": {
      "summary": { "type": "string" },
      "tags": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

---

## jarvis.json Schema (AI Lead Fills Content — Backend Reads Only)

```json
{
  "project_name": "",
  "description": "",
  "tech_stack": [],
  "team": [],
  "key_files": [],
  "known_issues": [],
  "goals": []
}
```

Backend reads this via `memory/jarvis_json.py`. **Never modify field names.**

---

## Non-Negotiables (Backend Must Follow)

- **Prompt caching:** Add `cache_control: { type: "ephemeral" }` to EVERY Claude API call's system prompt.
- **tool_use_id:** Always copy from `block.id` — never hardcode or generate.
- **Tool errors:** Tools ALWAYS return a dict. Never raise exceptions out of a tool. Return `{ "error": "message" }`.
- **Default AI mode:** `AI_MODE=local` in `.env`. No cloud calls without explicit `mode: "cloud"` in the WebSocket payload.
- **File watcher debounce:** 5 seconds minimum between events for the same file.

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...   # Never commit
AI_MODE=local                  # local | cloud
OLLAMA_BASE_URL=http://localhost:11434
PROJECT_PATH=.                 # Path JARVIS monitors
OLLAMA_GATE_THRESHOLD=0.7      # Confidence below this → escalate to cloud
```
