from backend.context.file_watcher import _classify_signal
from backend.context.project_context import (
    build_runtime_context,
    inspect_vault,
    route_query,
    search_project_notes,
)


def test_inspect_vault_reports_repo_second_brain():
    health = inspect_vault()

    assert health["has_wiki"] is True
    assert health["has_obsidian"] is True
    assert health["required_files"]["wiki/index.md"] is True
    assert health["note_count"] > 0


def test_route_query_uses_wiki_for_project_decisions():
    route = route_query("What decisions did we make about secure mode?")

    assert route["route"] == "wiki+memory"


def test_route_query_uses_code_for_file_questions():
    route = route_query("What does file_watcher.py do?")

    assert route["route"] == "code"


def test_route_query_uses_hybrid_for_relationship_questions():
    route = route_query("How does secure mode relate to file_watcher.py?")

    assert route["route"] == "hybrid"


def test_search_project_notes_finds_project_memory():
    results = search_project_notes(query="project memory", limit=3)

    assert results["returned"] >= 1
    assert any(result["path"].endswith("project-memory.md") for result in results["results"])


def test_build_runtime_context_includes_relevant_notes_for_context_questions():
    context = build_runtime_context("What context should Jarvis use for secure mode?")

    assert context["route"] == "wiki+memory"
    assert context["vault_health"]["has_wiki"] is True
    assert context["relevant_notes"]


def test_classify_signal_distinguishes_code_and_wiki_changes():
    assert _classify_signal("C:/repo/wiki/concepts/project-memory.md") == "wiki_note"
    assert _classify_signal("C:/repo/backend/context/file_watcher.py") == "code_change"
    assert _classify_signal("C:/repo/.obsidian/workspace.json") is None
    assert _classify_signal("C:/repo/raw/article.md") is None
