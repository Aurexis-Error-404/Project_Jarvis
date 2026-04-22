# JARVIS Capability Map

## Available Tools

- `read_codebase(file_path, lines?)`
  Reads the current codebase state from the active project workspace.
- `read_git_history(since, include_diff?, file_path?)`
  Reads commit history and optional diffs from the active git repository.
- `web_research(query, max_results?)`
  Fetches current web research results for time-sensitive technical questions.
- `generate_html_report(title, sections, research_data?, output_path?, report_type?, extra?)`
  Produces professional HTML reports from structured sections using one of six templates: `research`, `diagnosis`, `git_summary`, `audit`, `executive`, or `general`.
- `update_project_memory(field, action, value)`
  Persists explicit project decisions and notes into `jarvis.json`.
- `read_session_history(last_n_sessions?)`
  Reads recent session continuity from `jarvis.json`.
- `computer_automation(action, ...)`
  Available when `COMPUTER_AUTOMATION_ENABLED=1`. Controls mouse/keyboard or captures screenshots. Every call requires user consent.
- `browser_automation(action, url, ...)`
  Available when `BROWSER_AUTOMATION_ENABLED=1`. Navigates to allowlisted domains, reads DOM text, or captures screenshots. Every call requires user consent.

## Automatic Behaviors

- Orchestrator may fan out certain research or diagnosis requests to multiple sub-agents, then synthesize the result.
- Auto-research may iterate automatically on research-heavy queries when enabled, subject to quality, budget, and iteration caps.
- Quality retry may re-run a low-quality text-only answer once with adjusted settings.
- Consent gating applies to side-effecting automation tools before they execute.

These are system behaviors, not tools to call by name.

## Report Types

- `research`: literature review, benchmarking, upgrade paths, or landscape comparison.
- `diagnosis`: bug summary, post-mortem, root-cause report, or failure analysis.
- `git_summary`: changelog, release summary, or recent-commit rollup.
- `audit`: codebase review with findings grouped by severity.
- `executive`: concise high-level briefing for non-technical or decision-focused readers.
- `general`: fallback template when the request does not fit the other categories.

## Operating Rules

- Tool calls must be grounded in the user request and current project context.
- Prefer `read_codebase` over guessing.
- Prefer `read_git_history` for recent changes instead of inferring from current files.
- Pick `report_type` from user intent before generating a report; do not default to `research` unless the request is actually research-oriented.
- Only generate reports after collecting the underlying data needed for that report type.
- Mention computer/browser automation as available when enabled, not as always-on capabilities.
