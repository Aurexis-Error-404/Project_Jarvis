"""Per-session project workspace.

Replaces the process-global `os.environ["PROJECT_PATH"]` that used to leak
between concurrent WebSocket clients (see JARVIS_IMPLEMENTATION_PLAN.md
§5 and R-5 in §13.0).

Design:
  - `Workspace` wraps a resolved filesystem path and exposes helpers that
    tools call instead of reading the environment.
  - A `ContextVar` carries the active `Workspace` so sync tools (running in
    an executor) can read it without every tool growing a new parameter.
    The claude tool loop captures the current context via
    `contextvars.copy_context()` when scheduling executors, which propagates
    the ContextVar into the worker thread.
  - The `PROJECT_PATH` env var remains a process-wide default — consulted
    only when a session has not set its own path.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path


def _default_project_path() -> str:
    return str(Path(os.environ.get("PROJECT_PATH", ".")).resolve())


class Workspace:
    """Resolved project root for a single WebSocket session."""

    __slots__ = ("project_path",)

    def __init__(self, project_path: str | None = None):
        self.project_path = str(Path(project_path or _default_project_path()).resolve())

    def __repr__(self) -> str:
        return f"Workspace(project_path={self.project_path!r})"


# ContextVar default is a lazily-resolved Workspace. Reading `.get()` before
# any session has bound a workspace falls back to PROJECT_PATH (or cwd).
_ACTIVE: ContextVar[Workspace | None] = ContextVar("jarvis_workspace", default=None)


def set_active(workspace: Workspace):
    """Bind `workspace` as the active Workspace for the current async context.

    Returns the token from `ContextVar.set` so callers can reset on exit.
    """
    return _ACTIVE.set(workspace)


def reset_active(token) -> None:
    _ACTIVE.reset(token)


def current() -> Workspace:
    """Return the Workspace bound to the current context.

    Falls back to a default workspace rooted at `PROJECT_PATH` (or cwd) so
    call sites that run outside an AS session (CLI scripts, tests without
    fixtures) still work.
    """
    ws = _ACTIVE.get()
    if ws is None:
        return Workspace()
    return ws


def current_path() -> str:
    """Shortcut used by tools that only need the resolved root."""
    return current().project_path
