# tool_schema.md — All 6 JARVIS Tool Schemas

## Core Rule
The description field decides WHEN Claude calls the tool — not what it does.
Bad description = Claude calls the wrong tool or never calls it.
Every description must answer: what triggers this? what does NOT trigger this?
Disambiguation rules are mandatory — read_codebase and read_git_history WILL overlap without them.

---

## Tool 1: read_codebase

```python
{
    "name": "read_codebase",
    "description": """Read current file contents from the /src directory.

Call this tool when:
- Developer asks about current code, a specific function, or a class
- Diagnosing a bug and you need to see the actual file content
- Developer asks "what does X do" or "how is X implemented"
- You need to verify current variable types, function signatures, or imports
- Developer pastes a traceback and you need to read the file it references

Do NOT call this tool when:
- Developer asks what CHANGED recently (use read_git_history instead)
- Developer asks about git commits, diffs, or recent edits
- The file content is already in the current conversation context
- Developer asks about future plans or architecture decisions""",

    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path from repo root. Examples: 'src/preprocessor.py', 'src/models/efficientnet.py'. Use '.' to list all files in /src."
            },
            "lines": {
                "type": "string",
                "description": "Optional line range. Format: '80-120' to read lines 80 to 120. Omit to read entire file. Use when file is large and error traceback gives a specific line number."
            }
        },
        "required": ["file_path"]
    }
}
```

---

## Tool 2: read_git_history

```python
{
    "name": "read_git_history",
    "description": """Read recent git commits, diffs, and file change history.

Call this tool when:
- Developer asks what changed in their code recently
- Developer wants a commit message or PR description written
- Diagnosing a bug that may have been introduced by a recent change
- Generating a session briefing at startup (what happened since last session)
- Developer asks "when did X break" or "what did I change yesterday"

Do NOT call this tool when:
- Developer asks about current code state (use read_codebase instead)
- Developer asks about how code works or what it does (use read_codebase)
- Developer asks about general programming concepts
- Developer is asking about future plans or architecture""",

    "input_schema": {
        "type": "object",
        "properties": {
            "since": {
                "type": "string",
                "description": "Time range for history. Use '24h' for last 24 hours, '48h' for 2 days, '7d' for last week, or 'HEAD~3' for last 3 commits. Always provide this."
            },
            "include_diff": {
                "type": "boolean",
                "description": "Set true when diagnosing bugs — shows actual code changes. Set false for summaries and session briefings — just commit messages. Default false.",
                "default": False
            },
            "file_path": {
                "type": "string",
                "description": "Optional: specific file path to get history for. Omit to get history for all files in the repo."
            }
        },
        "required": ["since"]
    }
}
```

---

## Tool 3: web_research

```python
{
    "name": "web_research",
    "description": """Search the web for current technical information and research papers.

Call this tool when:
- Developer asks about a library, framework, or technique you don't have current knowledge of
- Generating the research report — you MUST call this to get current benchmarks
- Developer asks "what's the best X for Y" and the answer depends on recent research
- Developer asks about a model, dataset, or paper that may be newer than your training data

Do NOT call this tool when:
- The answer is in jarvis.json project context (use that instead — never search for what's already known)
- Developer asks about their own codebase (use read_codebase)
- Developer asks a general Python/programming question you can answer from knowledge
- Developer asks about project decisions already made (answer from memory, don't search)

IMPORTANT: When generating the research report, always inject project context into the search query.
BAD:  search("CNN architectures for image classification")
GOOD: search("EfficientNet satellite image classification small dataset Sentinel-2 2024")""",

    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query. For research reports, always include the project's specific model (EfficientNet-B3), dataset type (Sentinel-2, satellite), and task (pest detection, NDVI). Never use generic queries."
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return. Use 3 for quick lookups, 8 for research reports. Default 5.",
                "default": 5
            }
        },
        "required": ["query"]
    }
}
```

---

## Tool 4: generate_html_report

```python
{
    "name": "generate_html_report",
    "description": """Generate a formatted HTML research report and save it to disk.

Call this tool ONLY when:
- Developer explicitly asks for a research report
- Developer says "generate report", "create report", "make a report"
- After web_research has already been called and you have research results to include

Do NOT call this tool when:
- Developer asks a question (answer in text, don't generate a report)
- Developer asks for a summary (answer in text bullets)
- web_research has not been called yet — always research first, then report
- Developer is just asking about the project (use memory, not a report)

SEQUENCE: Always call web_research FIRST, then generate_html_report with the results.
Never call generate_html_report without research data to include.""",

    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Report title. Must be specific to the project. BAD: 'CNN Research Report'. GOOD: 'EfficientNet-B3 Upgrade Paths for Sentinel-2 Pest Detection'"
            },
            "sections": {
                "type": "array",
                "description": "Array of report sections. Each section has a heading and content.",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "content": {"type": "string", "description": "Markdown content for this section"}
                    },
                    "required": ["heading", "content"]
                }
            },
            "research_data": {
                "type": "string",
                "description": "Raw research results from web_research tool to include as citations or references section."
            },
            "output_path": {
                "type": "string",
                "description": "File path to save the report. Default: 'reports/jarvis_report_{timestamp}.html'",
                "default": "reports/jarvis_report.html"
            }
        },
        "required": ["title", "sections"]
    }
}
```

---

## Tool 5: update_project_memory

```python
{
    "name": "update_project_memory",
    "description": """Update jarvis.json with a new project decision, resolved question, or session note.

Call this tool ONLY when developer uses explicit commit phrases:
- "remember that"
- "we decided"
- "going with X"
- "lock this in"
- "note that"
- "add this to memory"

Do NOT call this tool when developer is thinking out loud:
- "I'm thinking about"
- "maybe we should"
- "what if we"
- "should we consider"
- "I wonder if"

If unsure whether to call: do NOT call it. Instead ask: "Should I remember this decision?"
Never call this tool twice in one response.
Never update rejected_approaches, decisions, or stack without an explicit commit phrase.""",

    "input_schema": {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "enum": ["decisions", "open_questions", "session_log", "project.current_focus", "rejected_approaches"],
                "description": "Which section of jarvis.json to update. Use 'decisions' for architecture choices, 'open_questions' to add or resolve a question, 'session_log' to log what was done."
            },
            "action": {
                "type": "string",
                "enum": ["append", "update", "resolve"],
                "description": "append: add new item. update: modify existing item. resolve: mark open_question as answered and remove it."
            },
            "value": {
                "type": "object",
                "description": "The data to write. For decisions: {what, chose, rejected, reason}. For open_questions: string. For session_log: {date, summary, files_touched}. For current_focus: string."
            }
        },
        "required": ["field", "action", "value"]
    }
}
```

---

## Tool 6: read_session_history

```python
{
    "name": "read_session_history",
    "description": """Read the session_log from jarvis.json to provide continuity across days.

Call this tool when:
- Session starts and developer asks "what were we working on?"
- Developer asks "what did we do last time?" or "where did we leave off?"
- Generating a daily briefing or session summary
- Developer asks about progress over the past few days

Do NOT call this tool when:
- Developer is asking about current code (use read_codebase)
- Developer is asking about recent git commits (use read_git_history)
- Session history is already loaded in the current context window
- Developer asks about a specific file or function (use read_codebase)

This tool is for narrative continuity — "what have we been doing" not "what does the code do."
For code-level history use read_git_history. For current state use read_codebase.""",

    "input_schema": {
        "type": "object",
        "properties": {
            "last_n_sessions": {
                "type": "integer",
                "description": "Number of most recent sessions to return. Use 1 for 'where did we leave off', 3 for weekly summary, 7 for full recent history. Default 3.",
                "default": 3
            }
        },
        "required": []
    }
}
```

---

## Disambiguation Quick Reference

When in doubt which tool to call, use this table:

| User says | Call this tool |
|---|---|
| "What does preprocessor.py do?" | read_codebase |
| "What changed in preprocessor.py?" | read_git_history |
| "What did I work on yesterday?" | read_session_history |
| "What's the best CNN for my project?" | web_research |
| "Generate a report on EfficientNet" | web_research → generate_html_report |
| "We're going with PostgreSQL" | update_project_memory |
| "I'm thinking of trying PostgreSQL" | NO TOOL — answer in text |

## Never Do This

```python
# WRONG — constructing tool_use_id yourself
tool_results.append({
    "tool_use_id": f"tool_{tool_name}_{i}",  # ← WILL CAUSE 400 ERROR
    "content": result
})

# RIGHT — always use block.id from Claude's response
tool_results.append({
    "tool_use_id": block.id,  # ← always this
    "content": result
})
```