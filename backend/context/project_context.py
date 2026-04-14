"""
Shared project-context helpers for JARVIS.

This module keeps the lightweight retrieval layer in one place:
- vault path resolution + health checks
- wiki note parsing/search/backlinks
- query routing between code and project knowledge
- compact per-query context bundles for prompts and proactive surfaces
"""

from __future__ import annotations

import ast
import os
import re
import time
from pathlib import Path

from backend.memory.jarvis_json import read as read_jarvis
from backend.memory.session_log import read as read_sessions

_REPO_ROOT = Path(__file__).parent.parent.parent
_REQUIRED_VAULT_FILES = ("wiki/index.md", "wiki/log.md", "wiki/setup.md")
_INDEX_TTL_SECONDS = 60.0
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z0-9_./-]+")
_CODE_HINT_RE = re.compile(
    r"([a-z0-9_./-]+\.(?:py|js|jsx|ts|tsx|json|html|css|md))|"
    r"\b(function|class|variable|line|import|traceback|stack trace|error|bug|"
    r"exception|fix|refactor|implement|file_watcher|claude_client)\b",
    re.IGNORECASE,
)
_CONTEXT_HINT_RE = re.compile(
    r"\b(architecture|design|decision|why|focus|roadmap|history|session|memory|"
    r"context|wiki|vault|obsidian|secure mode|project|how does .* relate)\b",
    re.IGNORECASE,
)
_PLAN_HINT_RE = re.compile(
    r"\b(plan|should|improve|enhance|roadmap|next steps?|future|what more|needs? to|"
    r"what if we|how would we|architecture vision|what.s (left|needed|missing)|"
    r"what (should|needs?|can) (we|i)|how (should|can) we|what else|what are the|"
    r"what needs|to be done|to implement|to add|to fix|to refactor)\b",
    re.IGNORECASE,
)

_note_cache = {"ts": 0.0, "vault": None, "notes": [], "by_path": {}, "backlinks": {}}


def invalidate_note_cache() -> None:
    """Force the note index to rebuild on the next _load_notes() call.

    Call this when a wiki note is saved so the 60s TTL cache does not serve
    stale content immediately after an edit.
    """
    _note_cache["ts"] = 0.0


def get_project_path() -> Path:
    return Path(os.environ.get("PROJECT_PATH", _REPO_ROOT)).resolve()


def get_vault_path() -> Path:
    explicit = os.environ.get("VAULT_PATH")
    if explicit:
        return Path(explicit).resolve()

    project_path = get_project_path()
    if (project_path / ".obsidian").exists() and (project_path / "wiki").exists():
        return project_path

    if (_REPO_ROOT / ".obsidian").exists() and (_REPO_ROOT / "wiki").exists():
        return _REPO_ROOT

    return project_path


def inspect_vault(vault_path: str | Path | None = None) -> dict:
    root = Path(vault_path).resolve() if vault_path else get_vault_path()
    required = {name: (root / name).exists() for name in _REQUIRED_VAULT_FILES}
    wiki_dir = root / "wiki"
    raw_dir = root / "raw"
    obsidian_dir = root / ".obsidian"
    note_count = len(list(wiki_dir.rglob("*.md"))) if wiki_dir.exists() else 0

    warnings = []
    if not obsidian_dir.exists():
        warnings.append("Missing .obsidian directory")
    if not wiki_dir.exists():
        warnings.append("Missing wiki directory")
    for rel_path, present in required.items():
        if not present:
            warnings.append(f"Missing {rel_path}")

    return {
        "vault_path": str(root),
        "healthy": not warnings,
        "has_obsidian": obsidian_dir.exists(),
        "has_wiki": wiki_dir.exists(),
        "has_raw": raw_dir.exists(),
        "required_files": required,
        "note_count": note_count,
        "warnings": warnings,
    }


def _parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed]
        except (ValueError, SyntaxError):
            inner = value[1:-1].strip()
            return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value.strip("'\"")
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    return value


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    data = {}
    current_key = None
    current_list: list[str] | None = None

    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if current_key and stripped.startswith("- "):
            current_list.append(stripped[2:].strip().strip("'\""))
            data[current_key] = list(current_list)
            continue

        current_key = None
        current_list = None

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            current_key = key
            current_list = []
            data[key] = current_list
            continue

        data[key] = _parse_scalar(value)

    return data, text[match.end():].lstrip()


def _normalize_terms(text: str) -> list[str]:
    return [term for term in _WORD_RE.findall(text.lower()) if len(term) > 1]


def _extract_summary(body: str) -> str:
    paragraphs = []
    for block in re.split(r"\n\s*\n", body):
        clean = " ".join(line.strip() for line in block.splitlines() if line.strip() and not line.lstrip().startswith("#"))
        if clean:
            paragraphs.append(clean)
    return (paragraphs[0] if paragraphs else "")[:280]


def _load_notes(force: bool = False) -> tuple[list[dict], dict[str, dict], dict[str, list[str]]]:
    root = get_vault_path()
    now = time.monotonic()
    if (
        not force
        and _note_cache["vault"] == str(root)
        and (now - _note_cache["ts"]) < _INDEX_TTL_SECONDS
    ):
        return _note_cache["notes"], _note_cache["by_path"], _note_cache["backlinks"]

    wiki_dir = root / "wiki"
    notes: list[dict] = []
    by_path: dict[str, dict] = {}

    if wiki_dir.exists():
        for path in sorted(wiki_dir.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            frontmatter, body = _parse_frontmatter(text)
            rel_path = str(path.relative_to(root)).replace("\\", "/")
            title = str(frontmatter.get("title") or path.stem.replace("-", " ").title())
            tags = [str(tag) for tag in frontmatter.get("tags", [])] if isinstance(frontmatter.get("tags"), list) else []
            links = []
            fm_links = frontmatter.get("links", [])
            if isinstance(fm_links, list):
                links.extend(str(link) for link in fm_links)
            links.extend(link.strip() for link in _WIKILINK_RE.findall(body))
            headings = [heading.strip() for heading in _HEADING_RE.findall(body)]
            note = {
                "path": rel_path,
                "title": title,
                "slug": path.stem,
                "type": str(frontmatter.get("type", "")),
                "tags": tags,
                "links": sorted({link for link in links if link}),
                "headings": headings,
                "summary": _extract_summary(body),
                "content": body.strip(),
                "frontmatter": frontmatter,
            }
            notes.append(note)
            by_path[rel_path] = note

    backlinks: dict[str, list[str]] = {}
    slug_lookup = {note["slug"].lower(): note["path"] for note in notes}
    title_lookup = {note["title"].lower(): note["path"] for note in notes}
    for note in notes:
        for link in note["links"]:
            target = slug_lookup.get(link.lower()) or title_lookup.get(link.lower())
            if target:
                backlinks.setdefault(target, []).append(note["path"])

    _note_cache.update(
        {
            "ts": now,
            "vault": str(root),
            "notes": notes,
            "by_path": by_path,
            "backlinks": backlinks,
        }
    )
    return notes, by_path, backlinks


def _make_excerpt(note: dict, query_terms: list[str]) -> str:
    body = note["content"]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not query_terms:
        return note["summary"]
    for line in lines:
        lowered = line.lower()
        if any(term in lowered for term in query_terms):
            return line[:280]
    return note["summary"]


def _score_note(note: dict, query_terms: list[str], tag_filter: list[str]) -> int:
    score = 0
    title_text = note["title"].lower()
    slug_text = note["slug"].lower()
    tag_text = " ".join(tag.lower() for tag in note["tags"])
    heading_text = " ".join(heading.lower() for heading in note["headings"])
    summary_text = note["summary"].lower()
    body_text = note["content"].lower()

    if tag_filter:
        missing = [tag for tag in tag_filter if tag.lower() not in tag_text]
        if missing:
            return 0
        score += 4 * len(tag_filter)

    for term in query_terms:
        if term in title_text:
            score += 6
        if term in slug_text:
            score += 5
        if term in tag_text:
            score += 4
        if term in heading_text:
            score += 3
        if term in summary_text:
            score += 2
        if term in body_text:
            score += 1

    if query_terms and all(term in body_text for term in query_terms):
        score += 3
    if note["path"].startswith("wiki/index"):
        score -= 1
    return score


def _resolve_note_path(note_path: str, by_path: dict[str, dict]) -> str | None:
    normalized = note_path.replace("\\", "/").strip("/")
    candidates = [normalized, f"wiki/{normalized}"]
    for candidate in candidates:
        if candidate in by_path:
            return candidate

    lowered = normalized.lower()
    for rel_path, note in by_path.items():
        if note["slug"].lower() == lowered or note["title"].lower() == lowered:
            return rel_path
    return None


def search_project_notes(
    query: str = "",
    note_path: str | None = None,
    tags: list[str] | str | None = None,
    include_related: bool = False,
    limit: int = 5,
    path_prefix: str | None = None,
) -> dict:
    notes, by_path, backlinks = _load_notes()
    # Filter to path_prefix if given; fall back to all notes if no matches
    if path_prefix:
        prefix_notes = [n for n in notes if n["path"].startswith(path_prefix)]
        notes = prefix_notes if prefix_notes else notes
    health = inspect_vault()
    if not health["has_wiki"]:
        return {"error": "Project wiki not available", "vault_health": health, "results": []}

    tag_filter = []
    if isinstance(tags, str) and tags.strip():
        tag_filter = [tag.strip() for tag in tags.split(",") if tag.strip()]
    elif isinstance(tags, list):
        tag_filter = [str(tag).strip() for tag in tags if str(tag).strip()]

    if note_path:
        resolved = _resolve_note_path(note_path, by_path)
        if not resolved:
            return {"error": f"Note not found: {note_path}", "vault_health": health, "results": []}
        note = by_path[resolved]
        result = _render_note_result(note, backlinks, include_body=True, include_related=include_related)
        return {
            "mode": "read",
            "query_route": "wiki+memory",
            "vault_health": health,
            "results": [result],
            "returned": 1,
        }

    query_terms = _normalize_terms(query)
    scored = []
    for note in notes:
        score = _score_note(note, query_terms, tag_filter)
        if score > 0 or (not query_terms and not tag_filter):
            scored.append((score, note))

    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    top = [_render_note_result(note, backlinks, excerpt=_make_excerpt(note, query_terms), include_related=include_related) for _, note in scored[: max(1, limit)]]

    return {
        "mode": "search",
        "query_route": "wiki+memory",
        "vault_health": health,
        "results": top,
        "returned": len(top),
    }


def _render_note_result(
    note: dict,
    backlinks: dict[str, list[str]],
    excerpt: str | None = None,
    include_body: bool = False,
    include_related: bool = False,
) -> dict:
    result = {
        "path": note["path"],
        "title": note["title"],
        "type": note["type"],
        "tags": note["tags"],
        "links": note["links"],
        "backlinks": sorted(backlinks.get(note["path"], [])),
        "headings": note["headings"][:8],
        "summary": note["summary"],
        "excerpt": excerpt or note["summary"],
    }
    if include_body:
        result["frontmatter"] = note["frontmatter"]
        result["content"] = note["content"]
    if include_related:
        related_paths = list(dict.fromkeys(result["links"] + result["backlinks"]))[:6]
        result["related"] = related_paths
    return result


def route_query(query: str) -> dict:
    lowered = query.lower()
    code_score = 0
    context_score = 0

    if _CODE_HINT_RE.search(query):
        code_score += 3
    if any(token in lowered for token in ("`", "/", "\\", ".py", ".js", ".jsx", ".ts", ".tsx")):
        code_score += 2
    if _CONTEXT_HINT_RE.search(query):
        context_score += 3
    if any(token in lowered for token in ("decision", "secure mode", "project context", "what were we", "second brain")):
        context_score += 2

    # Planning/future intent: boost context and flag analyses-first search
    search_analyses = bool(_PLAN_HINT_RE.search(query))
    if search_analyses:
        context_score += 4

    if code_score and context_score:
        route = "hybrid"
        reason = "Question mixes implementation detail with project knowledge."
    elif context_score > code_score:
        route = "wiki+memory"
        reason = "Question is about architecture, decisions, memory, or project context."
    else:
        route = "code"
        reason = "Question is primarily about implementation details or specific files."

    return {
        "route": route,
        "reason": reason,
        "code_score": code_score,
        "context_score": context_score,
        "search_analyses": search_analyses,
    }


def summarize_sessions(last_n_sessions: int = 3) -> str:
    session_result = read_sessions(last_n_sessions=last_n_sessions)
    sessions = session_result.get("sessions", [])
    if not sessions:
        return "No previous sessions recorded."

    lines = []
    for session in sessions:
        timestamp = session.get("timestamp", "unknown time")
        summary = session.get("summary", "")
        line = f"- {timestamp}: {session.get('messages', 0)} messages ({session.get('mode', 'unknown')} mode)"
        if summary:
            line += f"\n  Last topic: {summary}"
        lines.append(line)
    return "\n".join(lines)


def build_runtime_context(query: str, codebase_map: str = "") -> dict:
    jarvis = read_jarvis()
    routing = route_query(query)
    health = inspect_vault()

    search_query = query or jarvis.get("project", {}).get("current_focus", "")
    search_analyses = routing.get("search_analyses", False)
    note_summaries = []
    if health["has_wiki"]:
        if search_analyses:
            # Planning intent: pull from analyses/ first, then fill with general results
            analyses = search_project_notes(query=search_query, limit=2, path_prefix="wiki/analyses/")
            general = search_project_notes(query=search_query, limit=3)
            seen: set = set()
            combined: list = []
            for note in analyses.get("results", []) + general.get("results", []):
                if note["path"] not in seen:
                    seen.add(note["path"])
                    combined.append(note)
            top_notes = combined[:3]
        else:
            result = search_project_notes(query=search_query, limit=3)
            top_notes = result.get("results", [])[:3]
        for note in top_notes:
            note_summaries.append(
                {
                    "title": note["title"],
                    "path": note["path"],
                    "summary": note.get("excerpt") or note.get("summary", ""),
                    "tags": note.get("tags", []),
                }
            )

    trimmed_map = codebase_map.strip()
    if trimmed_map:
        lines = trimmed_map.splitlines()
        if len(lines) > 40:
            trimmed_map = "\n".join(lines[:40]) + f"\n... ({len(lines) - 40} more lines omitted)"

    return {
        "route": routing["route"],
        "route_reason": routing["reason"],
        "vault_health": health,
        "current_focus": jarvis.get("project", {}).get("current_focus", ""),
        "open_questions": jarvis.get("open_questions", []),
        "recent_sessions": summarize_sessions(last_n_sessions=3),
        "relevant_notes": note_summaries,
        "codebase_map": trimmed_map if routing["route"] in {"code", "hybrid"} else "",
    }


def format_runtime_context(context: dict) -> str:
    health = context.get("vault_health", {})
    notes = context.get("relevant_notes", [])
    note_lines = []
    for note in notes:
        tags = ", ".join(note.get("tags", []))
        suffix = f" | tags: {tags}" if tags else ""
        note_lines.append(f"- {note['title']} ({note['path']}): {note['summary']}{suffix}")

    open_questions = context.get("open_questions", [])
    open_text = "\n".join(f"- {question}" for question in open_questions) or "None."

    return (
        f"Route: {context.get('route', 'code')}\n"
        f"Why: {context.get('route_reason', '')}\n"
        f"Current focus: {context.get('current_focus', 'Not specified')}\n"
        f"Vault healthy: {health.get('healthy', False)}\n"
        f"Vault warnings: {', '.join(health.get('warnings', [])) or 'None'}\n"
        f"Relevant wiki notes:\n{chr(10).join(note_lines) or '- None found.'}\n"
        f"Open questions:\n{open_text}\n"
        f"Recent sessions:\n{context.get('recent_sessions', 'No previous sessions recorded.')}"
    )
