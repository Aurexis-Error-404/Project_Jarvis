# JARVIS x Obsidian Integration Guide

## Overview

Obsidian is a local-first Markdown knowledge base that stores everything as plain `.md` files. By pointing JARVIS at an Obsidian vault, you turn it into a queryable knowledge layer alongside your code — linking architecture decisions, meeting notes, research, and feature specs into a graph that JARVIS can search and reference.

**Why Obsidian fits JARVIS:**
- Local-first (aligns with JARVIS's secure mode — zero bytes leave the machine)
- Plain Markdown (JARVIS's `read_codebase` tool already reads `.md` files)
- Backlinks and tags create a knowledge graph without a database
- Vaults are just folders — no server, no setup, no vendor lock-in

---

## 1. Setting Up an Obsidian Vault for a Project

### Create the Vault

Create an Obsidian vault alongside or inside your project:

```
your-project/
  src/
  backend/
  docs/
  obsidian-vault/       <-- Obsidian vault root
    .obsidian/           <-- Obsidian config (auto-created)
    decisions/
    meetings/
    research/
    features/
    daily/
```

Or use a standalone vault at any path — JARVIS's "Add Project" button can point to it.

### Recommended Folder Structure

| Folder | Purpose | Example Note |
|--------|---------|-------------|
| `decisions/` | Architecture and design decisions | `2026-04-10-ai-model-routing.md` |
| `meetings/` | Standup logs, sprint reviews | `2026-04-11-standup.md` |
| `research/` | Papers, benchmarks, comparisons | `efficient-net-vs-resnet.md` |
| `features/` | One note per feature with status | `proactive-gate.md` |
| `daily/` | Daily logs, what you worked on | `2026-04-11.md` |

### Naming Conventions

- Time-stamped notes: `YYYY-MM-DD-topic.md` (e.g., `2026-04-10-websocket-contract.md`)
- Feature notes: `feature-name.md` (e.g., `proactive-gate.md`)
- Decision notes: `YYYY-MM-DD-decision-topic.md`

### Tags

Use consistent tags for JARVIS to filter on:

```markdown
---
tags: [decision, locked]
---
```

Common tags:
- `#decision` — finalized architecture choice
- `#open-question` — unresolved design question
- `#blocked` — feature blocked on something
- `#resolved` — previously open question, now answered
- `#research` — external research or benchmarks
- `#meeting` — standup or review notes

### Note Template

```markdown
---
tags: [decision]
date: 2026-04-10
status: locked
---

# AI Model Routing Decision

## Context
Gate runs 50+ times per hour. Must be free and local.

## Decision
- Gate: Ollama / CodeLlama (local, free)
- Error diagnosis: Gemini 2.5 Flash (quality-critical)
- Summaries: Groq Llama-3.3-70B (fast, structured)

## Alternatives Considered
- Claude API for gate (rejected: cost at 50+/hour)
- Sonnet for all tasks (rejected: overkill for summaries)

## Related
- [[proactive-gate]]
- [[websocket-contract]]
```

---

## 2. Using JARVIS with Obsidian Today (No Code Changes)

After the project path fix (BUG-1 in JARVIS_ISSUES_REPORT.md), JARVIS can already read Obsidian vaults:

### Step 1: Point JARVIS at the vault

Click "Add Project" in the JARVIS sidebar and select your Obsidian vault directory.

### Step 2: List all notes

Ask JARVIS:
> "List all files in this project"

JARVIS calls `read_codebase(".")` which lists all `.md` files in the vault. The `.obsidian/` config directory is automatically skipped (it contains no user notes).

### Step 3: Read specific notes

Ask JARVIS:
> "Read the decision note on AI model routing"

JARVIS calls `read_codebase("decisions/2026-04-10-ai-model-routing.md")` and returns the full note content.

### Step 4: Ask questions about your notes

> "What decisions have we locked in so far?"

JARVIS reads the vault, finds notes tagged `#decision`, and summarizes them.

### Limitations Today

- **No semantic search:** JARVIS can only read files by exact path, not search by content
- **No tag filtering:** Must read each file to find tags (no index)
- **No backlink traversal:** Cannot follow `[[wikilinks]]` across notes
- **Single project at a time:** JARVIS can only point at one directory (vault OR code, not both simultaneously)

---

## 3. Proposed Tool: `read_obsidian_notes` (Post-Sprint)

A dedicated tool that understands Obsidian's structure would solve all current limitations.

### Tool Schema

```json
{
  "name": "read_obsidian_notes",
  "description": "Search and read notes from an Obsidian vault. Supports tag filtering, keyword search, and backlink traversal.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Keyword search across note titles and content. Example: 'model routing decision'"
      },
      "tag": {
        "type": "string",
        "description": "Filter by tag. Example: 'decision', 'blocked', 'open-question'"
      },
      "backlinks_of": {
        "type": "string",
        "description": "Find all notes that link to this note. Example: 'proactive-gate'"
      },
      "limit": {
        "type": "integer",
        "description": "Max notes to return. Default 5."
      }
    },
    "required": []
  }
}
```

### Implementation Approach

**File:** `backend/tools/obsidian_reader.py`

```python
import os
import re
from pathlib import Path

VAULT_PATH = os.environ.get("VAULT_PATH", os.environ.get("PROJECT_PATH", "."))

def run(query=None, tag=None, backlinks_of=None, limit=5):
    vault = Path(VAULT_PATH)
    notes = list(vault.rglob("*.md"))

    # Skip .obsidian config
    notes = [n for n in notes if ".obsidian" not in n.parts]

    results = []
    for note in notes:
        content = note.read_text(encoding="utf-8", errors="ignore")
        score = 0

        # Tag filter
        if tag and f"#{tag}" not in content and tag not in _extract_frontmatter_tags(content):
            continue

        # Keyword search
        if query:
            score = sum(1 for word in query.lower().split() if word in content.lower())
            if score == 0:
                continue

        # Backlink search
        if backlinks_of:
            if f"[[{backlinks_of}]]" not in content:
                continue

        results.append({
            "path": str(note.relative_to(vault)),
            "title": _extract_title(content),
            "tags": _extract_frontmatter_tags(content),
            "score": score,
            "preview": content[:300],
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return {"notes": results[:limit], "total": len(results)}
```

### Integration Steps

1. Add tool to `backend/tools/__init__.py` — add schema to `TOOL_SCHEMAS` list
2. Add to `backend/tools/tool_dispatcher.py` — register in `_SYNC_TOOLS` dict
3. Add `VAULT_PATH` to `.env.example`
4. Update prompt rules in `backend/ai/prompts.py` (requires Rahul's approval):
   ```
   - read_obsidian_notes: search project knowledge base — decisions, meeting notes, research
   ```

---

## 4. Knowledge Graph Vision

### How Backlinks Create a Knowledge Graph

Obsidian's `[[wikilinks]]` create a directed graph across notes. JARVIS can traverse this to answer complex questions:

```
                    [[websocket-contract]]
                   /                      \
  [[proactive-gate]] ---- [[ai-model-routing]] ---- [[cost-controls]]
                   \                      /
                    [[file-watcher]]
```

**Example queries JARVIS could answer:**
- "What decisions are connected to the proactive gate?" -> Follow backlinks from `proactive-gate.md`
- "What's blocked right now?" -> Filter by `#blocked` tag across all notes
- "Summarize everything we decided this week" -> Filter by `#decision` tag + date range

### Dual-Vault Architecture (Future)

For advanced use, JARVIS could monitor TWO paths simultaneously:

| Path | Purpose |
|------|---------|
| `PROJECT_PATH` | Source code — `read_codebase`, `read_git_history` |
| `VAULT_PATH` | Obsidian vault — `read_obsidian_notes` |

This separates code from knowledge while letting JARVIS cross-reference both:

> "Which features in the vault don't have corresponding implementations in the codebase?"

---

## 5. Implementation Roadmap

| Phase | Task | Effort | Dependencies |
|-------|------|--------|-------------|
| **Phase 1** (Now) | Create vault structure for JARVIS project | 30 min | None |
| **Phase 1** (Now) | Use `read_codebase` to query vault notes | 0 min | BUG-1 fix (done) |
| **Phase 2** (Post-sprint) | Add `VAULT_PATH` to `.env.example` | 5 min | None |
| **Phase 2** (Post-sprint) | Implement `obsidian_reader.py` tool | 2 hrs | None |
| **Phase 2** (Post-sprint) | Register tool in dispatcher + schema | 30 min | `obsidian_reader.py` |
| **Phase 2** (Post-sprint) | Update prompt rules | 30 min | Rahul approval |
| **Phase 3** (Future) | Backlink graph traversal | 3 hrs | Phase 2 |
| **Phase 3** (Future) | Dual-vault (code + knowledge) | 2 hrs | Phase 2 |
| **Phase 3** (Future) | Auto-generate notes from JARVIS conversations | 4 hrs | Phase 2 |

### Phase 1: Works Today

After the project path fix, JARVIS can already read Obsidian vaults using `read_codebase`. No code changes needed — just create the vault and point JARVIS at it.

### Phase 2: Dedicated Tool

Build `read_obsidian_notes` with tag filtering and keyword search. This makes vault queries natural ("what decisions did we make about the gate?") instead of requiring exact file paths.

### Phase 3: Intelligence Layer

- **Graph traversal:** Follow `[[backlinks]]` to find related context automatically
- **Auto-note generation:** After a conversation, JARVIS writes a summary note to the vault
- **Proactive vault surfacing:** File watcher monitors the vault too, surfacing relevant notes when the developer works near a decision

---

## Quick Start Checklist

- [ ] Install Obsidian from [obsidian.md](https://obsidian.md)
- [ ] Create a vault folder (e.g., `project-root/obsidian-vault/`)
- [ ] Create folders: `decisions/`, `meetings/`, `research/`, `features/`, `daily/`
- [ ] Write your first decision note using the template above
- [ ] In JARVIS, click "Add Project" and select the vault folder
- [ ] Ask JARVIS: "List all files in this project"
- [ ] Ask JARVIS: "Read the note about [your topic]"
