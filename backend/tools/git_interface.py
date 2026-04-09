"""
read_git_history tool — reads git log and diffs via gitpython.

Parameters (from prompts/tool_schema.md — authoritative):
  since: str        — "24h", "48h", "7d", or "HEAD~3"
  include_diff: bool — include code diffs (default False)
  file_path: str    — optional: limit history to a specific file

NOT limit: int (that was backend CLAUDE.md — see CONFLICTS.md #3).
"""

import logging
from datetime import datetime, timedelta, timezone

import git

logger = logging.getLogger("jarvis.git_interface")

MAX_COMMITS = 50
MAX_DIFF_CHARS = 3000


def run(since: str, include_diff: bool = False, file_path: str = None) -> dict:
    try:
        repo = git.Repo(search_parent_directories=True)
        commits = _get_commits(repo, since, file_path)

        result = []
        for c in commits:
            entry = {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "author": str(c.author),
                "date": c.committed_datetime.isoformat(),
                "files_changed": list(c.stats.files.keys()) if c.stats else [],
            }
            if include_diff and c.parents:
                diff_text = repo.git.diff(c.parents[0].hexsha, c.hexsha)
                entry["diff"] = diff_text[:MAX_DIFF_CHARS]
                if len(diff_text) > MAX_DIFF_CHARS:
                    entry["diff"] += f"\n... (diff truncated at {MAX_DIFF_CHARS} chars)"
            result.append(entry)

        return {
            "commits": result,
            "count": len(result),
            "since": since,
            "file_filter": file_path,
        }

    except git.InvalidGitRepositoryError:
        return {"error": "Not a git repository"}
    except Exception as e:
        logger.error(f"git_interface error: {e}")
        return {"error": str(e)}


def _get_commits(repo: git.Repo, since: str, file_path: str = None):
    kwargs = {"max_count": MAX_COMMITS}
    if file_path:
        kwargs["paths"] = file_path

    since_lower = since.strip().lower()

    if since_lower.endswith("h"):
        hours = int(since_lower[:-1])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        # Use git's --after flag to filter at the source, not in Python
        kwargs["after"] = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        return list(repo.iter_commits(**kwargs))

    if since_lower.endswith("d"):
        days = int(since_lower[:-1])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        kwargs["after"] = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        return list(repo.iter_commits(**kwargs))

    if since_lower.startswith("head~"):
        n = int(since_lower[5:])
        kwargs["max_count"] = n
        return list(repo.iter_commits(**kwargs))

    logger.warning(f"Unrecognized since format: '{since}' — defaulting to last 10 commits")
    kwargs["max_count"] = 10
    return list(repo.iter_commits(**kwargs))
