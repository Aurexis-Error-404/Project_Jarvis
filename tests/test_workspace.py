"""Workspace regression coverage for per-session project isolation."""

from pathlib import Path

import pytest

from backend.context.workspace import Workspace, current_path, reset_active, set_active
from backend.tools import codebase_reader, tool_dispatcher


def test_codebase_reader_uses_active_workspace(tmp_path):
    project_dir = tmp_path / "workspace-reader"
    project_dir.mkdir()
    (project_dir / "alpha.txt").write_text("hello\n", encoding="utf-8")

    token = set_active(Workspace(str(project_dir)))
    try:
        result = codebase_reader.run(".")
    finally:
        reset_active(token)

    assert result["count"] == 1
    assert result["files"] == ["alpha.txt"]


@pytest.mark.asyncio
async def test_dispatcher_propagates_workspace_into_sync_tool_executor(tmp_path):
    project_dir = tmp_path / "workspace-dispatch"
    project_dir.mkdir()
    (project_dir / "beta.txt").write_text("world\n", encoding="utf-8")

    token = set_active(Workspace(str(project_dir)))
    try:
        result = await tool_dispatcher.dispatch_tool("read_codebase", {"file_path": "."})
    finally:
        reset_active(token)

    assert result["count"] == 1
    assert result["files"] == ["beta.txt"]


def test_current_path_falls_back_to_real_path():
    resolved = Path(current_path())
    assert resolved.is_absolute()
