"""
jarvis.json reader + writer.

Reads the actual jarvis.json schema (authoritative):
  project, decisions, open_questions, rejected_approaches, ai_config, websocket, session_log

NOT the schema from backend CLAUDE.md (project_name, tech_stack, etc.) — see CONFLICTS.md #6.
Backend reads only. jarvis.json field VALUES are owned by AI Lead + Docs team.
"""

import datetime
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("jarvis.jarvis_json")

# Resolve path relative to repo root (two levels up from this file)
_DEFAULT_PATH = Path(__file__).parent.parent.parent / "jarvis.json"

# Simple TTL read cache — avoids hitting disk on every file-watcher event
_CACHE_TTL = 5.0  # seconds
_cache: dict = {"data": None, "ts": 0.0}


def _append_wiki_log(action: str, description: str) -> None:
    """Append a one-line entry to wiki/log.md after each memory write. Silent on failure."""
    try:
        wiki_log = _DEFAULT_PATH.parent / "wiki" / "log.md"
        if not wiki_log.exists():
            return
        today = datetime.date.today().isoformat()
        entry = f"\n## [{today}] {action} | JARVIS Memory Update\n{description}\n"
        with wiki_log.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.warning(f"Wiki log sync failed (non-critical): {e}")


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

        wiki_log_action: str | None = None
        wiki_log_desc: str | None = None

        if field == "decisions" and action == "append":
            required = {"what", "chose", "rejected", "reason"}
            if not isinstance(value, dict) or not required.issubset(value.keys()):
                return {"error": "decisions value must have: what, chose, rejected, reason"}
            j["decisions"].append(value)
            wiki_log_action = "decision"
            wiki_log_desc = f"Decision recorded: {value.get('what', '')} → chose {value.get('chose', '')}"

        elif field == "open_questions" and action == "append":
            question = value if isinstance(value, str) else str(value)
            j["open_questions"].append(question)
            wiki_log_action = "question"
            wiki_log_desc = f"Open question added: {question}"

        elif field == "open_questions" and action == "resolve":
            question = value if isinstance(value, str) else str(value)
            before = len(j["open_questions"])
            j["open_questions"] = [q for q in j["open_questions"] if q != question]
            if len(j["open_questions"]) == before:
                return {"error": f"Question not found: {question}"}
            wiki_log_action = "resolve"
            wiki_log_desc = f"Question resolved: {question}"

        elif field == "session_log" and action == "append":
            j["session_log"].append(value)

        elif field == "rejected_approaches" and action == "append":
            approach = value if isinstance(value, str) else str(value)
            if approach not in j["rejected_approaches"]:
                j["rejected_approaches"].append(approach)

        elif field == "project.current_focus" and action == "update":
            j["project"]["current_focus"] = str(value)

        elif field == "ai_config.mode" and action == "update":
            if "ai_config" not in j:
                j["ai_config"] = {}
            j["ai_config"]["mode"] = str(value)

        elif field == "surface_metrics" and action == "increment":
            metric = str(value)
            if metric not in ("shown", "dismissed", "acted_on"):
                return {"error": f"Unknown surface metric '{metric}'. Expected: shown | dismissed | acted_on"}
            if "surface_metrics" not in j:
                j["surface_metrics"] = {"shown": 0, "dismissed": 0, "acted_on": 0}
            j["surface_metrics"].setdefault(metric, 0)
            j["surface_metrics"][metric] += 1

        elif field == "dismissed_surfaces" and action == "append":
            if "dismissed_surfaces" not in j:
                j["dismissed_surfaces"] = []
            entry = value if isinstance(value, dict) else {"file": str(value)}
            entry.setdefault(
                "timestamp",
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            j["dismissed_surfaces"].append(entry)
            # Keep only the 20 most recent dismissals
            if len(j["dismissed_surfaces"]) > 20:
                j["dismissed_surfaces"] = j["dismissed_surfaces"][-20:]

        else:
            return {"error": f"Unsupported field/action combination: {field}/{action}"}

        p = _resolve_path()
        p.write_text(json.dumps(j, indent=4), encoding="utf-8")

        # Invalidate cache so the next read picks up the fresh data
        _cache["data"] = None

        logger.info(f"jarvis.json updated: {field} ({action})")

        # Mirror decisions and questions to wiki/log.md (non-blocking)
        if wiki_log_action and wiki_log_desc:
            _append_wiki_log(wiki_log_action, wiki_log_desc)

        return {"status": "updated", "field": field, "action": action}

    except Exception as e:
        logger.error(f"jarvis_json.update error: {e}")
        return {"error": str(e)}
