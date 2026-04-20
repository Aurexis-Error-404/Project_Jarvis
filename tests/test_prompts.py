"""Prompt builder and prompt-log regression coverage."""

import json

from backend.ai import prompts
from backend.context.workspace import Workspace, reset_active, set_active
from backend.memory import prompt_log


def test_build_system_prompt_includes_optional_blocks(tmp_path):
    jarvis_path = tmp_path / "jarvis.json"
    jarvis_path.write_text(json.dumps({
        "project": {"name": "Demo", "stack": ["React", "FastAPI"], "current_focus": "Testing"},
        "decisions": [],
        "open_questions": [],
        "rejected_approaches": [],
    }), encoding="utf-8")

    prompt = prompts.build_system_prompt(
        jarvis_json_path=str(jarvis_path),
        codebase_map="Project files (1 total):\n  src/app.py",
        session_history="- yesterday: 3 messages",
        user_prefs="- keep answers short",
        failure_log="- prior failure",
        success_log="- prior success",
        capability_map="- read_codebase",
    )

    assert "<user_preferences>" in prompt
    assert "<recent_failures>" in prompt
    assert "<recent_successes>" in prompt
    assert "<capability_map>" in prompt


def test_build_system_prompt_handles_missing_or_bad_jarvis_json(tmp_path):
    bad_path = tmp_path / "jarvis.json"
    bad_path.write_text("{not-valid-json", encoding="utf-8")

    prompt = prompts.build_system_prompt(jarvis_json_path=str(bad_path))

    assert "Unknown Project" in prompt
    assert "<project_context>" in prompt


def test_prompt_log_loads_workspace_first_then_repo_fallback(tmp_path):
    project_dir = tmp_path / "project"
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "user_preferences.md").write_text("- prefer workspace prefs", encoding="utf-8")

    token = set_active(Workspace(str(project_dir)))
    try:
        loaded = prompt_log.load_prompt_context()
    finally:
        reset_active(token)

    assert loaded["user_prefs"] == "- prefer workspace prefs"
    assert "read_codebase" in loaded["capability_map"]


def test_post_query_hook_writes_success_and_failure_logs(tmp_path):
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True)

    token = set_active(Workspace(str(project_dir)))
    try:
        prompt_log.post_query_hook("first query", "all good", tool_calls_made=1)
        prompt_log.post_query_hook("second query", "API error: boom", tool_calls_made=0)
    finally:
        reset_active(token)

    success_log = (project_dir / ".claude" / "success_log.md").read_text(encoding="utf-8")
    failure_log = (project_dir / ".claude" / "failure_log.md").read_text(encoding="utf-8")

    assert "first query" in success_log
    assert "second query" in failure_log
