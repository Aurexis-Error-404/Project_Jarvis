"""
read_codebase tool — reads project files by path.

Parameters (from prompts/tool_schema.md — authoritative):
  file_path: str  — relative path from repo root, or "." to list all files
  lines: str      — optional line range, e.g. "80-120"

NOT path + depth (that was backend CLAUDE.md — see CONFLICTS.md #2).
"""

import logging
from pathlib import Path

logger = logging.getLogger("jarvis.codebase_reader")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", ".next"}
MAX_FILES = 50
MAX_LINES = 300  # truncate single-file reads at this line count


def run(file_path: str, lines: str = None) -> dict:
    """
    file_path="."       → list all files up to MAX_FILES limit
    file_path="src/x.py" → read that file, optionally filtered by line range
    lines="80-120"      → return only lines 80-120 (1-indexed)
    """
    try:
        if file_path == ".":
            return _list_files()
        else:
            return _read_file(file_path, lines)
    except Exception as e:
        logger.error(f"codebase_reader error: {e}")
        return {"error": str(e)}


def _list_files() -> dict:
    root = Path(".")
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        files.append(str(p).replace("\\", "/"))
        if len(files) >= MAX_FILES:
            break
    return {
        "files": files,
        "count": len(files),
        "note": f"Showing first {MAX_FILES} files. Use a specific path to read a file." if len(files) >= MAX_FILES else None,
    }


def _read_file(file_path: str, lines: str = None) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"error": f"File not found: {file_path}"}
    if not p.is_file():
        return {"error": f"Path is a directory, not a file: {file_path}. Use '.' to list files."}

    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"Could not read {file_path}: {e}"}

    all_lines = content.splitlines()
    total_lines = len(all_lines)

    if lines:
        try:
            parts = lines.split("-")
            if len(parts) != 2:
                return {"error": f"Invalid lines format: '{lines}'. Expected 'start-end', e.g. '80-120'."}
            start = max(1, int(parts[0].strip()))
            end = min(total_lines, int(parts[1].strip()))
            if start > end:
                return {"error": f"Invalid line range: start ({start}) > end ({end})."}
            selected = all_lines[start - 1 : end]
            return {
                "file": file_path,
                "content": "\n".join(selected),
                "lines_shown": f"{start}-{end}",
                "total_lines": total_lines,
            }
        except ValueError:
            return {"error": f"Invalid lines format: '{lines}'. Expected 'start-end', e.g. '80-120'."}

    if total_lines > MAX_LINES:
        truncated = "\n".join(all_lines[:MAX_LINES])
        return {
            "file": file_path,
            "content": truncated + f"\n... (truncated at line {MAX_LINES} of {total_lines}. Use lines= to read a specific range.)",
            "total_lines": total_lines,
            "truncated": True,
        }

    return {"file": file_path, "content": content, "total_lines": total_lines}
