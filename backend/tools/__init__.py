"""
TOOL_SCHEMAS — exact schemas from prompts/tool_schema.md (authoritative source).
These are passed to Claude on EVERY API call via tools= parameter.
"""

import os as _os

_COMPUTER_AUTOMATION_ENABLED = _os.environ.get("COMPUTER_AUTOMATION_ENABLED", "0").lower() in ("1", "true", "yes")
_BROWSER_AUTOMATION_ENABLED = _os.environ.get("BROWSER_AUTOMATION_ENABLED", "0").lower() in ("1", "true", "yes")

TOOL_SCHEMAS = [
    {
        "name": "read_codebase",
        "description": (
            "Read current file contents from the /src directory.\n\n"
            "Call this tool when:\n"
            "- Developer asks about current code, a specific function, or a class\n"
            "- Diagnosing a bug and you need to see the actual file content\n"
            "- Developer asks 'what does X do' or 'how is X implemented'\n"
            "- You need to verify current variable types, function signatures, or imports\n"
            "- Developer pastes a traceback and you need to read the file it references\n\n"
            "Do NOT call this tool when:\n"
            "- Developer asks what CHANGED recently (use read_git_history instead)\n"
            "- Developer asks about git commits, diffs, or recent edits\n"
            "- The file content is already in the current conversation context\n"
            "- Developer asks about future plans or architecture decisions"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Relative path from repo root. Examples: 'src/preprocessor.py', "
                        "'src/models/efficientnet.py'. Use '.' to list all files in /src."
                    ),
                },
                "lines": {
                    "type": "string",
                    "description": (
                        "Optional line range. Format: '80-120' to read lines 80 to 120. "
                        "Omit to read entire file. Use when file is large and error traceback "
                        "gives a specific line number."
                    ),
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "read_git_history",
        "description": (
            "Read recent git commits, diffs, and file change history.\n\n"
            "Call this tool when:\n"
            "- Developer asks what changed in their code recently\n"
            "- Developer wants a commit message or PR description written\n"
            "- Diagnosing a bug that may have been introduced by a recent change\n"
            "- Generating a session briefing at startup (what happened since last session)\n"
            "- Developer asks 'when did X break' or 'what did I change yesterday'\n\n"
            "Do NOT call this tool when:\n"
            "- Developer asks about current code state (use read_codebase instead)\n"
            "- Developer asks about how code works or what it does (use read_codebase)\n"
            "- Developer asks about general programming concepts\n"
            "- Developer is asking about future plans or architecture"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": (
                        "Time range for history. Use '24h' for last 24 hours, '48h' for 2 days, "
                        "'7d' for last week, or 'HEAD~3' for last 3 commits. Always provide this."
                    ),
                },
                "include_diff": {
                    "type": "boolean",
                    "description": (
                        "Set true when diagnosing bugs — shows actual code changes. "
                        "Set false for summaries and session briefings — just commit messages. "
                        "Default false."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Optional: specific file path to get history for. "
                        "Omit to get history for all files in the repo."
                    ),
                },
            },
            "required": ["since"],
        },
    },
    {
        "name": "web_research",
        "description": (
            "Search the web for current technical information and research papers.\n\n"
            "Call this tool when:\n"
            "- Developer asks about a library, framework, or technique you don't have current knowledge of\n"
            "- Generating the research report — you MUST call this to get current benchmarks\n"
            "- Developer asks 'what's the best X for Y' and the answer depends on recent research\n"
            "- Developer asks about a model, dataset, or paper that may be newer than your training data\n\n"
            "Do NOT call this tool when:\n"
            "- The answer is in jarvis.json project context (use that instead)\n"
            "- Developer asks about their own codebase (use read_codebase)\n"
            "- Developer asks a general Python/programming question you can answer from knowledge\n"
            "- Developer asks about project decisions already made (answer from memory, don't search)\n\n"
            "IMPORTANT: Always inject project context into the search query. "
            "BAD: search('CNN architectures'). "
            "GOOD: search('EfficientNet satellite image classification Sentinel-2 2024')"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. For research reports, always include the project's specific "
                        "model, dataset type, and task. Never use generic queries."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return. Use 3 for quick lookups, 8 for research reports. Default 5.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_html_report",
        "description": (
            "Generate a formatted HTML research report and save it to disk.\n\n"
            "Call this tool ONLY when:\n"
            "- Developer explicitly asks for a research report\n"
            "- Developer says 'generate report', 'create report', 'make a report'\n"
            "- After web_research has already been called and you have research results to include\n\n"
            "Do NOT call this tool when:\n"
            "- Developer asks a question (answer in text, don't generate a report)\n"
            "- Developer asks for a summary (answer in text bullets)\n"
            "- web_research has not been called yet — always research first, then report\n"
            "- Developer is just asking about the project (use memory, not a report)\n\n"
            "SEQUENCE: Always call web_research FIRST, then generate_html_report with the results. "
            "Never call generate_html_report without research data to include."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Report title. Must be specific to the project. "
                        "BAD: 'CNN Research Report'. "
                        "GOOD: 'EfficientNet-B3 Upgrade Paths for Sentinel-2 Pest Detection'"
                    ),
                },
                "sections": {
                    "type": "array",
                    "description": "Array of report sections. Each section has a heading and content.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {
                                "type": "string",
                                "description": "Markdown content for this section",
                            },
                        },
                        "required": ["heading", "content"],
                    },
                },
                "research_data": {
                    "type": "string",
                    "description": "Raw research results from web_research tool to include as citations or references section.",
                },
                "output_path": {
                    "type": "string",
                    "description": "File path to save the report. Default: 'reports/jarvis_report_{timestamp}.html'",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["research", "diagnosis", "git_summary", "audit", "executive", "general"],
                    "description": (
                        "Picks the report template. Default 'research'. "
                        "Use 'diagnosis' for error/bug summaries, 'git_summary' for changelogs, "
                        "'audit' for codebase reviews with severity groupings, 'executive' for "
                        "single-page briefings, 'general' when none of the above fits."
                    ),
                },
                "extra": {
                    "type": "object",
                    "description": (
                        "Type-specific extras rendered by the template. "
                        "diagnosis: {severity, impact, root_cause, summary}. "
                        "git_summary: {range_label}. "
                        "audit: {severity_counts: {critical, high, medium, low}, summary}. "
                        "executive: {headline}. "
                        "research: {abstract, tags}. "
                        "general: (none)."
                    ),
                },
            },
            "required": ["title", "sections"],
        },
    },
    {
        "name": "update_project_memory",
        "description": (
            "Update jarvis.json with a new project decision, resolved question, or session note.\n\n"
            "Call this tool ONLY when developer uses explicit commit phrases:\n"
            "- 'remember that'\n"
            "- 'we decided'\n"
            "- 'going with X'\n"
            "- 'lock this in'\n"
            "- 'note that'\n"
            "- 'add this to memory'\n\n"
            "Do NOT call this tool when developer is thinking out loud:\n"
            "- 'I'm thinking about'\n"
            "- 'maybe we should'\n"
            "- 'what if we'\n"
            "- 'should we consider'\n"
            "- 'I wonder if'\n\n"
            "If unsure whether to call: do NOT call it. Instead ask: 'Should I remember this decision?' "
            "Never call this tool twice in one response. "
            "Never update rejected_approaches, decisions, or stack without an explicit commit phrase."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": [
                        "decisions",
                        "open_questions",
                        "session_log",
                        "project.current_focus",
                        "rejected_approaches",
                    ],
                    "description": (
                        "Which section of jarvis.json to update. Use 'decisions' for architecture "
                        "choices, 'open_questions' to add or resolve a question, 'session_log' to "
                        "log what was done."
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": ["append", "update", "resolve"],
                    "description": (
                        "append: add new item. update: modify existing item. "
                        "resolve: mark open_question as answered and remove it."
                    ),
                },
                "value": {
                    "type": "object",
                    "description": (
                        "The data to write. For decisions: {what, chose, rejected, reason}. "
                        "For open_questions: string. "
                        "For session_log: {date, summary, files_touched}. "
                        "For current_focus: string."
                    ),
                },
            },
            "required": ["field", "action", "value"],
        },
    },
    {
        "name": "read_session_history",
        "description": (
            "Read the session_log from jarvis.json to provide continuity across days.\n\n"
            "Call this tool when:\n"
            "- Session starts and developer asks 'what were we working on?'\n"
            "- Developer asks 'what did we do last time?' or 'where did we leave off?'\n"
            "- Generating a daily briefing or session summary\n"
            "- Developer asks about progress over the past few days\n\n"
            "Do NOT call this tool when:\n"
            "- Developer is asking about current code (use read_codebase)\n"
            "- Developer is asking about recent git commits (use read_git_history)\n"
            "- Session history is already loaded in the current conversation window\n"
            "- Developer asks about a specific file or function (use read_codebase)\n\n"
            "This tool is for narrative continuity — 'what have we been doing' not 'what does the code do.' "
            "For code-level history use read_git_history. For current state use read_codebase."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "last_n_sessions": {
                    "type": "integer",
                    "description": (
                        "Number of most recent sessions to return. Use 1 for 'where did we leave off', "
                        "3 for weekly summary, 7 for full recent history. Default 3."
                    ),
                },
            },
            "required": [],
        },
    },
]

# ─── Optional consent-gated tools (§7.2) ─────────────────────────────────
# Registered only when the corresponding env flag is on. Every call passes
# through the dispatcher's consent gate before the tool runs.

if _COMPUTER_AUTOMATION_ENABLED:
    TOOL_SCHEMAS.append({
        "name": "computer_automation",
        "description": (
            "Control the user's mouse, keyboard, or take a screenshot. "
            "EVERY call prompts the user for consent before running — never "
            "call this speculatively. Use only when the developer has "
            "explicitly asked for a UI action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["screenshot", "click", "type", "key", "move"]},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "text": {"type": "string"},
                "key": {"type": "string"},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
            },
            "required": ["action"],
        },
    })

if _BROWSER_AUTOMATION_ENABLED:
    TOOL_SCHEMAS.append({
        "name": "browser_automation",
        "description": (
            "Navigate to a URL on an allowlisted domain and read DOM text or "
            "take a screenshot. EVERY call prompts the user for consent. "
            "Requests to non-allowlisted domains fail closed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["navigate", "dom_text", "screenshot"]},
                "url": {"type": "string"},
                "selector": {"type": "string"},
                "max_chars": {"type": "integer"},
                "full_page": {"type": "boolean"},
            },
            "required": ["action", "url"],
        },
    })

# OpenAI-compatible format for Gemini + Groq (converted from Anthropic format above)
OAI_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOL_SCHEMAS
]
