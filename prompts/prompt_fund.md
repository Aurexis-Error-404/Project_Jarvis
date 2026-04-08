# prompt_fund.md — Prompt Engineering Fundamentals

## Core
Claude is a prediction machine. Your prompt is the input to that distribution.
Vague input = high variance output. Precise input = low variance output.

---

## Six Rules

### 1. Specificity over generality

BAD (random quality):
```
"Analyse the error and suggest a fix"
```

GOOD (consistent quality):
```
"Identify the specific line causing this error. Name the file path, line number,
and exact variable with the wrong type. Give the fix as 1-3 lines of code
specific to the files provided."
```

### 2. XML tags — the underused technique

XML tags set clear section boundaries Claude reliably follows.

```xml
<project_context>
Project: Intelligent Pest Risk Estimation System
Stack: EfficientNet-B3, Sentinel-2, Streamlit, FastAPI
Current focus: NDVI computation accuracy on cloudy tiles
</project_context>

<decisions>
- Switched ResNet50 → EfficientNet-B3 (better on small satellite datasets)
- Using Isolation Forest over One-Class SVM
- FocalLoss(gamma=2) instead of CrossEntropy (class imbalance)
</decisions>

<rules>
- Every answer must reference specific files and line numbers
- Never suggest decisions already made (see decisions above)
- Never say "according to your memory" — just use the information
</rules>
```

### 3. Conditional rules Claude reliably follows

Use if/then structures that are mutually exclusive and exhaustive.

```python
# BAD — ambiguous
"Call update_project_memory when the user makes decisions."

# GOOD — explicit triggers, no ambiguity
"""Call update_project_memory ONLY when the user says one of:
- "remember that", "we decided", "going with", "lock this in", "note that"

Do NOT call update_project_memory when the user says:
- "I'm thinking about", "maybe", "what if", "should we", "considering"

If unsure: do NOT call it. Ask 'Should I remember this?' instead."""
```

### 4. Preventing hallucinations with constraints

Hallucinations happen when Claude doesn't have the information but answers anyway.
Fix: explicit constraints that tell Claude what to do when it doesn't know.

```python
# Pattern 1: Explicit fallback
"If you don't have the specific file content to answer this,
say 'I need to read [filename] first' and call read_codebase."

# Pattern 2: Confidence gate
"Only name specific line numbers if you have actual file content
from the read_codebase tool result. If you don't have it, say
the file needs to be read first."

# Pattern 3: Evidence requirement
"Every claim in the diagnosis section must be supported by either:
(a) a line from the traceback provided, or
(b) a specific line from the file content provided.
Do not diagnose from general knowledge alone."

# Pattern 4: Known/unknown split
"Structure your response as:
WHAT I KNOW (from the files provided): ...
WHAT I'D NEED TO CHECK: ...
RECOMMENDATION: ..."
```

### 5. Controlling output format

```python
# Technique 1: Show exact format
"Respond in exactly this format, no other text:
CAUSE: [one sentence, must name the exact file and line]
FIX: [1-3 lines of code]
ALSO CHECK: [other affected files, or 'none']"

# Technique 2: JSON with a threat
"Respond with ONLY valid JSON. No other text before or after.
No markdown code blocks. No explanation. Just the JSON object:
{
  'should_surface': true or false,
  'confidence': 0.0 to 1.0,
  'reason': 'one sentence'
}"

# Technique 3: Negative constraints
"Do NOT start with 'Here are', 'Based on', 'I can see', or 'According to'.
Do NOT use bullet points. Write in direct sentences."

# Technique 4: Length constraints
"Each bullet: maximum 15 words. Maximum 3 bullets total.
If you have nothing project-specific to say: return an empty string."
```

### 6. Regression testing — run on every version change

---

## Regression Test Suite

### Test Cases

```python
test_cases = [
    {
        "name": "memory read — known fact",
        "input": "What database are we using?",
        "must_contain": ["SQLite"],
        "must_not_contain": ["according to", "based on your", "I see that"],
        "must_not_call_tool": ["update_project_memory"]
    },
    {
        "name": "memory update — explicit commit",
        "input": "We're going with PostgreSQL, remember that",
        "must_call_tool": "update_project_memory",
        "tool_input_must_contain": "PostgreSQL"
    },
    {
        "name": "memory update — thinking aloud (should NOT update)",
        "input": "I'm thinking maybe we should use PostgreSQL",
        "must_not_call_tool": ["update_project_memory"]
    },
    {
        "name": "rejected tech — should not suggest ResNet",
        "input": "What CNN should I use for image classification?",
        "must_contain": ["EfficientNet"],
        "must_not_contain": ["ResNet50"]
    },
    {
        "name": "specificity check — error diagnosis must name files",
        "input": "TypeError: float object cannot be interpreted as integer — Traceback: preprocessor.py line 89",
        "must_contain": ["line", ".py"],
        "must_not_contain": ["generally", "typically", "in most cases"]
    }
]
```

### The Fixed Runner (tool call checking included)

```python
import anthropic, json

client = anthropic.Anthropic()

def call_claude_for_test(system_prompt: str, user_input: str) -> anthropic.types.Message:
    """Returns full response object so we can check both text and tool calls."""
    return client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }],
        tools=TOOL_DEFINITIONS,  # import from tool_schema.py
        messages=[{"role": "user", "content": user_input}]
    )

def get_text(response) -> str:
    """Extract text content from response."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""

def get_tool_calls(response) -> list[dict]:
    """Extract all tool calls from response."""
    return [
        {"name": block.name, "input": block.input}
        for block in response.content
        if block.type == "tool_use"
    ]

def run_tests(system_prompt: str, version: str):
    print(f"\n=== System Prompt {version} Regression Results ===")
    passed = failed = 0

    for test in test_cases:
        response = call_claude_for_test(system_prompt, test["input"])
        text = get_text(response)
        tool_calls = get_tool_calls(response)
        tool_names_called = [tc["name"] for tc in tool_calls]

        ok = True
        failures = []

        # Check must_contain
        for phrase in test.get("must_contain", []):
            if phrase.lower() not in text.lower():
                failures.append(f"missing text: '{phrase}'")
                ok = False

        # Check must_not_contain
        for phrase in test.get("must_not_contain", []):
            if phrase.lower() in text.lower():
                failures.append(f"found forbidden text: '{phrase}'")
                ok = False

        # Check must_call_tool  ← THIS WAS MISSING IN THE OLD RUNNER
        if "must_call_tool" in test:
            expected_tool = test["must_call_tool"]
            if expected_tool not in tool_names_called:
                failures.append(f"expected tool call '{expected_tool}' — not called. Called: {tool_names_called}")
                ok = False
            else:
                # Check tool input content if specified
                if "tool_input_must_contain" in test:
                    required = test["tool_input_must_contain"]
                    tool_input_str = json.dumps([
                        tc["input"] for tc in tool_calls
                        if tc["name"] == expected_tool
                    ])
                    if required.lower() not in tool_input_str.lower():
                        failures.append(f"tool '{expected_tool}' called but input missing '{required}'")
                        ok = False

        # Check must_not_call_tool  ← THIS WAS MISSING IN THE OLD RUNNER
        for forbidden_tool in test.get("must_not_call_tool", []):
            if forbidden_tool in tool_names_called:
                failures.append(f"tool '{forbidden_tool}' was called but should NOT have been")
                ok = False

        if ok:
            print(f"  ✓ {test['name']}")
            passed += 1
        else:
            print(f"  ✗ {test['name']}")
            for f in failures:
                print(f"      → {f}")
            failed += 1

    print(f"\nResult: {passed}/{passed+failed} passed")
    print(f"{'All tests pass — prompt is stable.' if failed == 0 else 'Fix failing tests before next feature.'}")
    return failed == 0

# Usage:
# all_pass = run_tests(MY_SYSTEM_PROMPT, "v3")
# if not all_pass:
#     print("Do NOT proceed — fix the prompt first")
```

### When to Run Tests

Run the full suite:
- Before finalizing any prompt version (document the version number)
- After every edit to the system prompt
- After any change to tool schemas
- At Hour 6 (first end-to-end test), Hour 18 (go/no-go gate), Hour 36 (feature freeze)

Target: all 5 tests passing before Hour 18 gate.
If test 2 or 3 (memory tests) are failing at Hour 12: pause feature work, fix the trigger rules first.