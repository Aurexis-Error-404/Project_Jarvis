---
title: "Wiki Setup & Conventions"
type: concept
created: 2026-04-11
updated: 2026-04-11
tags: [meta, conventions, setup]
sources: []
links: []
confidence: high
---

# Wiki Setup & Conventions

This document defines how the wiki is organized, named, and maintained. Read this if you're trying to understand the structure.

## Folder Map

| Folder | Purpose | Who writes | Naming |
|--------|---------|-----------|--------|
| `raw/` | Immutable source documents | Rama (drop files here) | Any format, descriptive names |
| `raw/assets/` | Images and attachments | Rama / Obsidian Web Clipper | As-downloaded |
| `wiki/sources/` | One summary page per raw source | Claude (LLM) | `{source-name}.md` kebab-case |
| `wiki/entities/` | People, tools, projects, orgs | Claude (LLM) | `{entity-name}.md` kebab-case |
| `wiki/concepts/` | Ideas, patterns, frameworks | Claude (LLM) | `{concept-name}.md` kebab-case |
| `wiki/analyses/` | Comparisons, syntheses, filed queries | Claude (LLM) | `{date}-{name}.md` or `{name}.md` |

## Page Rules

1. **Every page gets YAML frontmatter** — title, type, created, updated, tags, sources, links, confidence
2. **Every page starts with a one-paragraph summary** — readable standalone
3. **Cross-references use `[[wiki-links]]`** — Obsidian-compatible
4. **Claims trace to sources** — either a raw source or marked as inference/synthesis
5. **Contradictions are explicit** — never silently override old info

## Tag Taxonomy

Start simple, evolve as needed:

- **Domain tags**: `ai`, `frontend`, `backend`, `architecture`, `devtools`, `personal`, `research`
- **Status tags**: `active`, `archived`, `draft`, `disputed`
- **Meta tags**: `meta`, `conventions`, `setup`

Tags are lowercase, hyphenated for multi-word.

## Confidence Levels

- **high** — Directly stated in a primary source, verified, or well-established
- **medium** — Inferred from multiple sources, or stated in a secondary source
- **low** — Speculative, single-source, or potentially outdated

## Workflow Cheat Sheet

| You want to... | Do this |
|----------------|---------|
| Add new knowledge | Drop file in `raw/`, tell Claude "ingest this" |
| Ask a question | Just ask — Claude reads the wiki to answer |
| Get a health check | Say "lint the wiki" |
| File an insight | Ask Claude to save a query result as an analysis page |
| Browse the wiki | Open Obsidian, check `wiki/index.md` or use graph view |

## Obsidian Tips

- **Graph view** shows the shape of your wiki — hubs, orphans, clusters
- **Dataview plugin** can query frontmatter fields across pages
- **Web Clipper** converts articles to markdown for `raw/`
- Set attachment folder to `raw/assets/` in Obsidian settings
- Bind "Download attachments" to a hotkey (e.g., Ctrl+Shift+D)

## Evolution

This setup will evolve. As the wiki grows:
- Tag taxonomy may expand
- New page types may emerge
- Search tooling may be needed (e.g., qmd for hybrid search)
- The schema in CLAUDE.md will be updated to reflect changes

The wiki is a living system. Conventions serve it, not the other way around.
