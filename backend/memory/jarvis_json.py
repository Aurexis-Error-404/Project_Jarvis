"""
jarvis.json reader + writer.

Reads the actual jarvis.json schema (authoritative):
  project, decisions, open_questions, rejected_approaches, ai_config, websocket, session_log

NOT the schema from backend CLAUDE.md (project_name, tech_stack, etc.) — see CONFLICTS.md #6.
Backend reads only. jarvis.json field VALUES are owned by AI Lead + Docs team.
"""

import json
import logging
import time
from pathlib import Path

from backend.ai.security import sanitize_for_logging

logger = logging.getLogger("jarvis.jarvis_json")

# Resolve path relative to repo root (two levels up from this file)
_DEFAULT_PATH = Path(__file__).parent.parent.parent / "jarvis.json"

# Simple TTL read cache — avoids hitting disk on every file-watcher event
_CACHE_TTL = 5.0  # seconds
_cache: dict = {"data": None, "ts": 0.0}


def _resolve_path(path: str = None) -> Path:
    if path:
        return Path(path)
    return _DEFAULT_PATH


def read(path: str = None) -> dict:
    """Read and return the full jarvis.json as a dict."""
    # Only cache the default path — custom paths are used for tests
    if path is None:
        now = time.monotonic()
        if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
            return _cache["data"]

    try:
        p = _resolve_path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        if path is None:
            _cache["data"] = data
            _cache["ts"] = time.monotonic()
        return data
    except FileNotFoundError:
        logger.error(f"jarvis.json not found at {_resolve_path(path)}")
        return {"error": "jarvis.json not found"}
    except json.JSONDecodeError as e:
        logger.error(f"jarvis.json is invalid JSON: {e}")
        return {"error": f"Invalid JSON in jarvis.json: {e}"}
    except Exception as e:
        logger.error(f"jarvis_json.read error: {e}")
        return {"error": str(e)}


def update(field: str, action: str, value) -> dict:
    """
    Update a field in jarvis.json.

    field:  "decisions" | "open_questions" | "session_log" |
            "project.current_focus" | "rejected_approaches"
    action: "append" | "update" | "resolve"
    value:  the data to write (see tool_schema.md for per-field shape)
    """
    try:
        j = read()
        if "error" in j:
            return j

        # Defense-in-depth: scrub anything key-shaped before it hits disk.
        # Callers should not be passing secrets, but a leaked API key in a
        # decision's `reason` or in a session_log entry would persist forever.
        value = sanitize_for_logging(value)

        if field == "decisions" and action == "append":
            if not isinstance(value, dict) or not all(k in value for k in ("what", "chose", "rejected", "reason")):
                return {"error": "decisions value must have: what, chose, rejected, reason"}
            j["decisions"].append(value)

        elif field == "open_questions" and action == "append":
            question = value if isinstance(value, str) else str(value)
            j["open_questions"].append(question)

        elif field == "open_questions" and action == "resolve":
            question = value if isinstance(value, str) else str(value)
            before = len(j["open_questions"])
            j["open_questions"] = [q for q in j["open_questions"] if q != question]
            if len(j["open_questions"]) == before:
                return {"error": f"Question not found: {question}"}

        elif field == "session_log" and action == "append":
            j["session_log"].append(value)

        elif field == "rejected_approaches" and action == "append":
            approach = value if isinstance(value, str) else str(value)
            if approach not in j["rejected_approaches"]:
                j["rejected_approaches"].append(approach)

        elif field == "project.current_focus" and action == "update":
            j["project"]["current_focus"] = str(value)

        else:
            return {"error": f"Unsupported field/action combination: {field}/{action}"}

        p = _resolve_path()
        p.write_text(json.dumps(j, indent=4), encoding="utf-8")

        # Invalidate cache so the next read picks up the fresh data
        _cache["data"] = None

        logger.info(f"jarvis.json updated: {field} ({action})")
        return {"status": "updated", "field": field, "action": action}

    except Exception as e:
        logger.error(f"jarvis_json.update error: {e}")
        return {"error": str(e)}
