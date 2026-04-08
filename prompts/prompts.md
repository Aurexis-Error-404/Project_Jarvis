# prompts.md — JARVIS Specific Prompts

## The 4 prompts you must write and iterate

1. Gate Prompt (Ollama) — should_surface decision
2. Surface Prompt (Haiku) — 2-3 bullet cards
3. Error Diagnosis section (in system prompt)
4. Research Report instruction (in system prompt)

---

## Prompt 1: Gate Prompt (Ollama / CodeLlama)

Used by: proactive engine (runs 50+ times/hour in background)
Model: Ollama / CodeLlama
Output: JSON only — {should_surface, confidence, reason}

### The Prompt

```python
GATE_PROMPT = """Respond with ONLY a JSON object. No explanation. No code blocks. No markdown. Just JSON.

{"should_surface": true or false, "confidence": 0.0 to 1.0, "reason": "one sentence max"}

Rules:
- should_surface true: file is actively being worked on AND relates to current focus
- should_surface false: config file, dependency, test file, file not touched in 10+ minutes, file surfaced in last 5 minutes
- confidence above 0.7 required for should_surface true
- reason must be one sentence, specific to the file and focus

Signal:
File changed: {file_path}
File type: {file_extension}
Last surfaced: {last_surfaced_minutes} minutes ago
Current project focus: {current_focus}
Recent files touched: {recent_files}

JSON:"""
```

### Why "JSON:" at the end
It primes Ollama to begin its response with `{` — reduces markdown fence wrapping by ~80%.

### 5 Scenario Tests — Run All Before Hour 18

```python
gate_test_cases = [
    {
        "name": "active focus file — should surface",
        "inputs": {
            "file_path": "src/preprocessor.py",
            "file_extension": ".py",
            "last_surfaced_minutes": 15,
            "current_focus": "NDVI computation accuracy on cloudy tiles",
            "recent_files": ["preprocessor.py", "cloud_mask.py"]
        },
        "expect_surface": True,
        "expect_confidence_above": 0.7
    },
    {
        "name": "config file — should NOT surface",
        "inputs": {
            "file_path": ".env",
            "file_extension": ".env",
            "last_surfaced_minutes": 999,
            "current_focus": "NDVI computation accuracy on cloudy tiles",
            "recent_files": [".env"]
        },
        "expect_surface": False
    },
    {
        "name": "irrelevant file — should NOT surface",
        "inputs": {
            "file_path": "requirements.txt",
            "file_extension": ".txt",
            "last_surfaced_minutes": 999,
            "current_focus": "NDVI computation accuracy on cloudy tiles",
            "recent_files": ["requirements.txt"]
        },
        "expect_surface": False
    },
    {
        "name": "surfaced 3 mins ago — should NOT surface (cooldown)",
        "inputs": {
            "file_path": "src/preprocessor.py",
            "file_extension": ".py",
            "last_surfaced_minutes": 3,
            "current_focus": "NDVI computation accuracy on cloudy tiles",
            "recent_files": ["preprocessor.py"]
        },
        "expect_surface": False
    },
    {
        "name": "unrelated .py file — borderline",
        "inputs": {
            "file_path": "src/data_loader.py",
            "file_extension": ".py",
            "last_surfaced_minutes": 30,
            "current_focus": "NDVI computation accuracy on cloudy tiles",
            "recent_files": ["preprocessor.py", "data_loader.py"]
        },
        "expect_surface": False,
        "note": "data_loader is not directly related to cloud masking — gate should be conservative"
    }
]

def run_gate_tests(gate_prompt_template: str):
    passed = 0
    for test in gate_test_cases:
        prompt = gate_prompt_template.format(**test["inputs"])
        raw = call_ollama(prompt)
        result = parse_ollama_json(raw)

        surface = result.get("should_surface", False)
        confidence = result.get("confidence", 0.0)
        expected = test["expect_surface"]

        ok = (surface == expected)
        if test.get("expect_confidence_above") and surface:
            ok = ok and (confidence >= test["expect_confidence_above"])

        status = "PASS" if ok else "FAIL"
        print(f"  {status}: {test['name']}")
        print(f"         got: should_surface={surface}, confidence={confidence:.2f}")
        print(f"         reason: {result.get('reason', 'none')}")
        if ok:
            passed += 1

    print(f"\nGate: {passed}/{len(gate_test_cases)} passed")
```

---

## Prompt 2: Surface Prompt (Claude Haiku)

Used by: overlay card, shown to developer when gate fires
Model: claude-haiku-4-5-20251001
Output: 2-3 bullets, each ≤15 words, project-specific

### The Prompt

```python
SURFACE_PROMPT = """You are generating a proactive context card for a developer.

Project context:
- Current focus: {current_focus}
- Stack: {stack}
- Recent decisions: {recent_decisions}

File signal:
- File changed: {file_path}
- Recent git activity on this file: {git_summary}

Generate exactly 2-3 bullet points. Rules:
- Each bullet: maximum 15 words
- Every bullet must reference a specific function name, variable, line number, or commit detail from the context above
- Do NOT write generic advice like "consider refactoring" or "check for edge cases"
- Do NOT start with "You" or "Consider" or "Remember"
- If you have nothing project-specific to say: return empty string — do not fabricate relevance

Format: return ONLY the bullets, one per line, starting with •
No preamble, no explanation, no heading."""
```

### Quality Test for Surface Prompt

Run this test. Read the output. Apply the specificity filter:

```
BAD output (generic — prompt is not working):
• Consider reviewing this file for potential issues
• You were recently working on this area
• Check for edge cases in your implementation

GOOD output (project-specific — prompt is working):
• cloud_mask.py last modified here — median imputation not applied to this path
• NDVI NaN pattern from Tuesday's commit not yet handled in preprocessor
• FocalLoss gamma value not validated against this file's class distribution
```

If your output looks like BAD: the `{git_summary}` or `{current_focus}` injection is not working.
Debug the injection first. The prompt text is fine — it's the variables that are empty.

---

## Prompt 3: Error Diagnosis (Section in System Prompt)

This goes into the `<behavior_rules>` section of the static system prompt.

```
<error_diagnosis_rules>
When a developer pastes a traceback or error:
1. Call read_codebase for the file named in the traceback BEFORE diagnosing
2. Call read_git_history with include_diff=true to check if a recent commit introduced this
3. Only after reading the actual file: respond in exactly this format —

CAUSE: [one sentence — must name the exact file, line number, and variable or type that is wrong]
FIX: [1-3 lines of code — specific to the actual file content you read]
ALSO CHECK: [other files likely affected, or "none"]

Rules:
- Never diagnose from the traceback alone — always read the file
- CAUSE line must contain a filename ending in .py and a line number
- FIX must be actual code, not a description of what to do
- If you cannot identify the specific line: say "I need to read [file] at lines [range]" and call the tool

BAD CAUSE: "The error is caused by a type mismatch in the data pipeline"
GOOD CAUSE: "Line 89 in preprocessor.py — variable cloud_threshold is float but filter_tiles() expects int"
</error_diagnosis_rules>
```

---

## Prompt 4: Research Report (Section in System Prompt)

This goes into the `<tool_rules>` section of the static system prompt.
This single instruction is what makes the report mention EfficientNet-B3 instead of generic SOTA.

```
<research_report_rules>
When generating a research report:

Step 1 — Call web_research with a project-specific query.
WRONG query: "best CNN for image classification"
RIGHT query:  "EfficientNet-B3 alternatives satellite image classification small dataset Sentinel-2 2024"
The query MUST include: the current model ({project.stack} includes this), the dataset type (Sentinel-2), the constraint (small dataset).

Step 2 — Call web_research again with a follow-up query on the specific limitation.
Example: "EfficientNet-B4 vs B3 training time small satellite dataset benchmark"

Step 3 — Call generate_html_report with sections:
  - Executive Summary (3 sentences, must mention current stack)
  - Current Approach (what we're using and why — from jarvis.json decisions)
  - Research Findings (from web_research results)
  - Recommendations (MUST reference current model by name, MUST acknowledge rejected approaches, MUST name specific upgrade path)
  - Next Steps (2-3 actionable items grounded in open_questions from jarvis.json)

The Recommendations section MUST:
- Name the project's current model (EfficientNet-B3) explicitly
- Suggest an upgrade path that acknowledges the small dataset constraint
- NOT suggest ResNet50 or any approach in rejected_approaches
- Reference at least one specific paper or benchmark from the web_research results
</research_report_rules>
```

---

## Ollama Variants (Local Mode)

Ollama / CodeLlama has a 4K context window and weaker instruction following.
These are shorter, more directive versions of the above prompts.

### Ollama Surface Prompt (shorter)

```python
OLLAMA_SURFACE_PROMPT = """Project: {project_name}. Focus: {current_focus}. File changed: {file_path}.

Write 2 bullet points about this file change. Rules:
- Each bullet under 12 words
- Must mention a specific function or variable name from: {key_symbols}
- No generic advice

Bullets only, starting with •:"""
```

### Why simpler for Ollama
CodeLlama 7B struggles with long instruction sets. Fewer rules = more reliable output.
The key_symbols variable (list of function/class names from the changed file) compensates for Ollama's weaker reasoning.

### Getting key_symbols
```python
import ast

def extract_symbols(file_path: str) -> list[str]:
    """Extract function and class names from a Python file for Ollama context."""
    try:
        with open(file_path) as f:
            tree = ast.parse(f.read())
        return [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        ][:10]  # max 10 symbols to stay in context budget
    except:
        return []
```