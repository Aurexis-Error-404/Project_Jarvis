"""Append-only audit log for consent decisions and gated tool calls (§7.2).

One line per entry (JSONL) in `<workspace>/.claude/audit.log`. The log
is:
  * **Never rotated by this module.** External log management handles
    size; we just append.
  * **Redacted.** Payloads pass through `sanitize_for_logging` so any
    API keys pasted into a screenshot prompt, etc., don't land on disk.
  * **Best-effort.** Disk failure is logged, never raised — consent
    decisions must not be blocked by an unwritable audit log, but the
    user still gets the dialog result and the warning surfaces in logs.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from backend.ai.security import sanitize_for_logging

logger = logging.getLogger("jarvis.audit")

_AUDIT_RELPATH = ".claude/audit.log"


def _resolve_log_path(project_path: str | None) -> Path:
    root = Path(project_path) if project_path else Path(os.getcwd())
    return root / _AUDIT_RELPATH


def append_audit(
    project_path: str | None,
    action: str,
    payload: dict[str, Any],
    *,
    decision: str,
) -> None:
    """Append one JSONL entry to the workspace audit log."""
    entry = {
        "ts": time.time(),
        "action": action,
        "decision": decision,
        "payload": sanitize_for_logging(payload) if isinstance(payload, dict) else str(payload),
    }
    path = _resolve_log_path(project_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning(f"audit log write failed: {e}")
