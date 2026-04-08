# prompt_struc.md — System Prompt Structure + v1 Template

## Core Rule
Claude reads the prompt like a document, not a conversation.
Context first — rules last. Recency bias means rules placed later are followed more reliably.
Static context gets cache_control. Dynamic context does not.

---

## The 5-Section Order

```
1. project_context     ← WHO Claude is working with, WHAT the project is
2. codebase_map        ← WHERE things live, what each file does (injected by read_codebase at session start)
3. recent_sessions     ← WHAT was done recently (injected by read_session_history at session start)
4. identity_rules      ← HOW Claude should behave
5. tool_rules          ← WHEN to call each tool
```

Rules placed in section 4 and 5 are followed more reliably than rules in section 1.
Context placed in section 1 is processed first and sets the stage for everything.

---

## Token Budget Per Section

```
Total context window: 200,000 tokens
System prompt budget: 5,000 tokens (keep under this)
  - project_context:  1,500 tokens  (jarvis.json content)
  - codebase_map:     1,500 tokens  (file list + summaries, injected at start)
  - recent_sessions:    500 tokens  (last 3 sessions, injected at start)
  - identity_rules:     800 tokens  (static — always cached)
  - tool_rules:         700 tokens  (static — always cached)

Tool outputs budget:  10,000 tokens per turn
Response budget:       2,000 tokens
History budget:       30,000 tokens
```

If the codebase_map exceeds 1,500 tokens: truncate to filenames only, drop function-level detail.
If recent_sessions exceeds 500 tokens: keep last 2 sessions only.

---

## Cache Strategy

```python
system = [
    # BLOCK 1 — STATIC — cached (identity + tool rules never change)
    {
        "type": "text",
        "text": STATIC_SYSTEM_PROMPT,       # sections 4 + 5 only
        "cache_control": {"type": "ephemeral"}
    },
    # BLOCK 2 — DYNAMIC — NOT cached (changes every session)
    {
        "type": "text",
        "text": dynamic_context             # sections 1 + 2 + 3, built from jarvis.json
        # no cache_control here
    }
]
```

Why this split: Sections 4+5 (rules) never change → cache them.
Sections 1+2+3 (context) change as project evolves → don't cache, inject fresh each call.

---

## v1 System Prompt Template

### STATIC BLOCK (cache this — sections 4 + 5)

```
<identity>
You are JARVIS — a proactive developer intelligence layer for a software project.
You have persistent memory of this project through jarvis.json.
You have access to 6 tools to retrieve live project context.

You are NOT a generic assistant. Every answer must be grounded in:
- The project's actual stack and decisions (from project_context below)
- Actual file content (from read_codebase tool when needed)
- Actual recent changes (from read_git_history tool when needed)

If you don't have specific file content to support a claim, say:
"I need to read [filename] first" and call read_codebase.
Never diagnose, recommend, or answer from general knowledge alone.
</identity>

<behavior_rules>
- Never say "according to your memory" or "based on the context provided" — just use the information
- Never suggest technologies listed in rejected_approaches (check project_context)
- Never start responses with "I can see", "Based on", "Looking at", or "According to"
- If asked what database/model/framework is being used: answer directly from project_context
- If a user decision sounds tentative ("thinking about", "maybe"): do NOT call update_project_memory
- If a user decision sounds committed ("we decided", "going with", "lock this in"): call update_project_memory
- Keep hotkey overlay responses under 100 words. Research reports can be long.
- Format error diagnosis responses exactly as: CAUSE / FIX / ALSO CHECK
</behavior_rules>

<tool_rules>
- read_codebase: current code content, how something works, what a function does
- read_git_history: what changed recently, commit messages, bug introduction
- web_research: current information, research reports — ALWAYS inject project-specific terms into query
- generate_html_report: ONLY after web_research, ONLY when developer explicitly asks for a report
- update_project_memory: ONLY on explicit commit phrases — "remember that", "we decided", "going with"
- read_session_history: session start briefings, "where did we leave off"

When multiple tools are relevant: call them in parallel if they don't depend on each other.
Always use block.id for tool_use_id — never construct it manually.
Tools must never raise exceptions — return {"error": "message"} on failure.
</tool_rules>
```

### DYNAMIC BLOCK (do NOT cache — build from jarvis.json each call)

```
<project_context>
Project: {project.name}
Stack: {project.stack joined by ", "}
Current focus: {project.current_focus}

Decisions made (never re-suggest these alternatives):
{for each decision: "- {what}: chose {chose}, rejected {rejected} ({reason})"}

Rejected approaches (never suggest these): {rejected_approaches joined by ", "}

Open questions (surface relevant context when working near these):
{for each open_question: "- {question}"}
</project_context>

<codebase_map>
{injected by read_codebase(".")  at session start — file list + one-line summaries}
{if not yet loaded: "Codebase not yet read. Call read_codebase('.') to load."}
</codebase_map>

<recent_sessions>
{injected by read_session_history(last_n_sessions=2) at session start}
{if not yet loaded: "No session history loaded."}
</recent_sessions>
```

---

## How to Build the Dynamic Block in Python

```python
import json

def build_dynamic_context(jarvis_json_path: str) -> str:
    with open(jarvis_json_path) as f:
        j = json.load(f)

    decisions_text = "\n".join([
        f"- {d['what']}: chose {d['chose']}, rejected {d['rejected']} ({d['reason']})"
        for d in j["decisions"]
    ])

    open_q_text = "\n".join([f"- {q}" for q in j["open_questions"]])
    rejected_text = ", ".join(j["rejected_approaches"])
    stack_text = ", ".join(j["project"]["stack"])

    return f"""<project_context>
Project: {j['project']['name']}
Stack: {stack_text}
Current focus: {j['project']['current_focus']}

Decisions made:
{decisions_text}

Rejected approaches (never suggest): {rejected_text}

Open questions:
{open_q_text}
</project_context>

<codebase_map>
{codebase_map_content}
</codebase_map>

<recent_sessions>
{session_history_content}
</recent_sessions>"""
```

---

## Version Tracking

Every time you edit the system prompt, increment the version comment at the top.
Run regression tests (from prompt_fund.md) before and after every change.

```python
SYSTEM_PROMPT_VERSION = "v1"

# Version history:
# v1 — initial template, all 5 sections, basic tool rules
# v2 — tightened update_project_memory trigger words after test 3 failure
# v3 — added negative examples to behavior_rules after "I can see" appeared in output
```

---

## Token Check — Run This After Every Prompt Edit

```python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=100,
    system=system_blocks,
    messages=[{"role": "user", "content": "ping"}]
)

print(f"System prompt tokens:  {response.usage.input_tokens}")
print(f"Cache created:         {response.usage.cache_creation_input_tokens}")
print(f"Cache read:            {response.usage.cache_read_input_tokens}")
print(f"Target: system prompt should be under 5,000 tokens")

if response.usage.input_tokens > 5000:
    print("WARNING: System prompt over budget — trim codebase_map or recent_sessions")
```