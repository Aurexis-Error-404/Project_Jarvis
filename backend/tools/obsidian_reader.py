"""
Runtime tool for reading project knowledge from the wiki/Obsidian vault.
"""

from backend.context.project_context import search_project_notes


def run(
    query: str = "",
    note_path: str = "",
    tags=None,
    include_related: bool = False,
    limit: int = 5,
) -> dict:
    return search_project_notes(
        query=query,
        note_path=note_path or None,
        tags=tags,
        include_related=include_related,
        limit=limit,
    )
