"""Helpers for optional prompt-side markdown context in `.claude/`."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from backend.context.workspace import current_path

logger = logging.getLogger("jarvis.prompt_log")

MAX_PROMPT_CONTEXT_CHARS = 2500
MAX_LOG_ENTRIES = 10


def _repo_claude_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude"


def _workspace_claude_dir(project_path: str | None = None) -> Path:
    return Path(project_path or current_path()).resolve() / ".claude"


def _read_text(path: Path) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:
        logger.warning(f"Failed to read prompt context file {path}: {e}")
        return ""


def _read_prompt_file(filename: str, project_path: str | None = None) -> str:
    workspace_dir = _workspace_claude_dir(project_path)
    candidates = [workspace_dir / filename]
    repo_dir = _repo_claude_dir()
    if workspace_dir != repo_dir:
        candidates.append(repo_dir / filename)

    for candidate in candidates:
        content = _read_text(candidate)
        if content:
            return content[:MAX_PROMPT_CONTEXT_CHARS]
    return ""


def _write_log_entry(filename: str, entry: str, project_path: str | None = None) -> None:
    target_dir = _workspace_claude_dir(project_path)
    if not target_dir.exists():
        target_dir = _repo_claude_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        existing = _read_text(path)
        lines = [line for line in existing.splitlines() if line.strip()]
        lines.append(entry)
        path.write_text(
            "\n".join(lines[-MAX_LOG_ENTRIES:]) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Failed to write prompt log {filename}: {e}")


def load_prompt_context(project_path: str | None = None) -> dict[str, str]:
    return {
        "user_prefs": _read_prompt_file("user_preferences.md", project_path),
        "capability_map": _read_prompt_file("capability_map.md", project_path),
        "failure_log": _read_prompt_file("failure_log.md", project_path),
        "success_log": _read_prompt_file("success_log.md", project_path),
    }


def post_query_hook(query: str, response: str, tool_calls_made: int = 0,
                    project_path: str | None = None) -> None:
    summary = " ".join(query.strip().split())[:120] or "<empty query>"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not response or response.startswith("API error:") or "I ran into a loop" in response:
        _write_log_entry(
            "failure_log.md",
            f"- {timestamp} | tools={tool_calls_made} | query={summary}",
            project_path=project_path,
        )
        return

    _write_log_entry(
        "success_log.md",
        f"- {timestamp} | tools={tool_calls_made} | query={summary}",
        project_path=project_path,
    )
