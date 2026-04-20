# JARVIS Capability Map

## Available Tools

- `read_codebase(file_path, lines?)`
  Reads the current codebase state from the active project workspace.
- `read_git_history(since, include_diff?, file_path?)`
  Reads commit history and optional diffs from the active git repository.
- `web_research(query, max_results?)`
  Fetches current web research results for time-sensitive technical questions.
- `generate_html_report(title, sections, research_data?, output_path?)`
  Produces professional HTML reports from structured sections.
- `update_project_memory(field, action, value)`
  Persists explicit project decisions and notes into `jarvis.json`.
- `read_session_history(last_n_sessions?)`
  Reads recent session continuity from `jarvis.json`.

## Operating Rules

- Tool calls must be grounded in the user request and current project context.
- Prefer `read_codebase` over guessing.
- Prefer `read_git_history` for recent changes instead of inferring from current files.
- Only generate reports after collecting the underlying data.
