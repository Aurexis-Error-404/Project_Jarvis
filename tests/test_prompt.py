from openai import OpenAI
import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

def _make_client():
    """Return (client, model). Try Gemini first; fall back to Groq on quota issues."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    if gemini_key:
        return (
            OpenAI(api_key=gemini_key,
                   base_url="https://generativelanguage.googleapis.com/v1beta/openai/"),
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "gemini"
        )
    if groq_key:
        return (
            OpenAI(api_key=groq_key,
                   base_url="https://api.groq.com/openai/v1"),
            os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "groq"
        )
    raise RuntimeError("No API key found. Set GEMINI_API_KEY or GROQ_API_KEY in .env")

client, MODEL, PROVIDER = _make_client()

with open("jarvis.json") as f:
    JARVIS = json.load(f)

# ── System Prompt v1 ──────────────────────────────────────────────────────────
# Structure: static block (identity + behavior_rules + tool_rules) — never mutate
#          + dynamic block (project_context built fresh from jarvis.json)
# See prompts/prompt_struc.md for template. See prompts/prompt_fund.md for tests.

STATIC_SYSTEM_PROMPT = """<identity>
You are JARVIS — a proactive developer intelligence layer for a software project.
You have persistent memory of this project through jarvis.json.
You have access to tools to retrieve live project context.

You are NOT a generic assistant. Every answer must be grounded in:
- The project's actual stack and decisions (from project_context below)
- Actual file content (from read_codebase tool when needed)

If asked what model/engine is used for the proactive gate: answer "Ollama/CodeLlama".
Never diagnose, recommend, or answer from general knowledge alone.
</identity>

<behavior_rules>
- Never say "according to your memory" or "based on the context provided" — just use the information
- Never suggest technologies listed in rejected_approaches
- Never start responses with "I can see", "Based on", "Looking at", or "According to"
- If the user asks a question (what, which, how, why, tell me, explain): answer directly in text. Do NOT call any tool.
- If a user decision sounds tentative ("thinking about", "maybe", "what if", "should we", "I wonder if"): do NOT call update_project_memory
- If a user decision sounds committed: you MUST call update_project_memory immediately. Committed phrases: "remember that", "we decided", "going with", "lock this in", "note that", "add this to memory"
</behavior_rules>

<tool_rules>
- update_project_memory: ONLY call when the user explicitly commits a decision using: "remember that", "we decided", "going with X", "lock this in", or "note that". This is required on those phrases, not optional.
- NEVER call update_project_memory when answering a question or information request — questions do not trigger memory writes.
- Do NOT call update_project_memory when the user says: "thinking about", "maybe", "what if", "should we", "considering", "I wonder".
- read_codebase: current code content, how something works, what a function does
- read_git_history: what changed recently, commit messages, bug introduction
- read_session_history: session start briefings, "where did we leave off"
</tool_rules>"""


def build_dynamic_context() -> str:
    j = JARVIS
    decisions_text = "\n".join([
        f"- {d['what']}: chose {d['chose']}, rejected {d['rejected']} ({d['reason']})"
        for d in j.get("decisions", [])
    ])
    open_q_text = "\n".join([f"- {q}" for q in j.get("open_questions", [])])
    rejected_text = ", ".join(j.get("rejected_approaches", []))
    stack_text = ", ".join(j.get("project", {}).get("stack", []))

    return f"""<project_context>
Project: {j['project']['name']}
Stack: {stack_text}
Current focus: {j['project']['current_focus']}

Decisions made (never re-suggest these alternatives):
{decisions_text}

Rejected approaches (never suggest): {rejected_text}

Open questions:
{open_q_text}
</project_context>"""


SYSTEM_PROMPT = STATIC_SYSTEM_PROMPT + "\n\n" + build_dynamic_context()

# ── Tools (OpenAI format) ─────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_project_memory",
            "description": (
                'Update jarvis.json with a confirmed project decision. '
                'CALL THIS TOOL when user says: "remember that", "we decided", '
                '"going with", "lock this in", "note that". '
                'Do NOT call when user says: "thinking about", "maybe", "what if", "should we".'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["decisions", "open_questions", "session_log", "rejected_approaches"]
                    },
                    "value": {
                        "type": "object",
                        "description": (
                            "Must always be an object, never a string. "
                            "For field='decisions': {\"what\":\"topic\",\"chose\":\"chosen option\",\"rejected\":\"rejected option\",\"reason\":\"why\"}. "
                            "For field='open_questions': {\"question\":\"the question text\"}. "
                            "For field='rejected_approaches': {\"approach\":\"name of approach\"}. "
                            "For field='session_log': {\"note\":\"log entry text\"}."
                        )
                    }
                },
                "required": ["field", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_codebase",
            "description": "Read current file contents from /src. Call when developer asks about current code or diagnosing a bug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "lines": {"type": "string"}
                },
                "required": ["file_path"]
            }
        }
    }
]

# ── Helpers ───────────────────────────────────────────────────────────────────
PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM  = "\033[2m"
results = {"passed": 0, "failed": 0, "skipped": 0}


def call_claude(user_input, use_tools=True):
    global client, MODEL, PROVIDER
    kwargs = dict(
        model=MODEL,
        max_tokens=300,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]
    )
    if use_tools:
        kwargs["tools"] = TOOLS
    for attempt in range(2):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and PROVIDER == "gemini":
                groq_key = os.getenv("GROQ_API_KEY")
                if groq_key:
                    print(f"  {DIM}Gemini quota exhausted — switching to Groq fallback...{RESET}")
                    client = OpenAI(api_key=groq_key,
                                    base_url="https://api.groq.com/openai/v1")
                    MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
                    PROVIDER = "groq"
                    kwargs["model"] = MODEL
                else:
                    raise
            else:
                raise
    return client.chat.completions.create(**kwargs)


def get_text(r):
    return r.choices[0].message.content or ""


def get_tool_calls(r):
    tool_calls = r.choices[0].message.tool_calls or []
    return [tc for tc in tool_calls if tc.type == "function"]


def check(name, ok, detail=""):
    if ok:
        results["passed"] += 1
        print(f"{PASS} {name}")
    else:
        results["failed"] += 1
        print(f"{FAIL} {name}")
        if detail:
            print(f"      {DIM}-> {detail}{RESET}")


def skip(name, reason=""):
    results["skipped"] += 1
    print(f"{SKIP} {name} {DIM}({reason}){RESET}")


def parse_ollama_json(raw):
    import re
    raw = re.sub(r'```(?:json)?\n?', '', raw).replace('```', '')
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}
    try:
        return json.loads(match.group())
    except:
        try:
            return json.loads(match.group().replace("'", '"'))
        except:
            return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}


print(f"\n{BOLD}=== JARVIS test_prompt.py (System Prompt v1) ==={RESET}")
print(f"  {DIM}Provider: {PROVIDER} | Model: {MODEL}{RESET}\n")

# 1. API connectivity
print(f"{BOLD}[1] API Connectivity{RESET}")
try:
    t0 = time.time()
    r = call_claude("Reply with exactly: API_OK", use_tools=False)
    latency = int((time.time() - t0) * 1000)
    text = get_text(r)
    check("API call succeeds", "API_OK" in text, f"got: {text[:60]}")
    check(f"Latency under 5s ({latency}ms)", latency < 5000)
    check("Input tokens counted", r.usage.prompt_tokens > 0)
    print(f"  {DIM}tokens in: {r.usage.prompt_tokens} | out: {r.usage.completion_tokens}{RESET}")
except Exception as e:
    check("API call succeeds", False, str(e))
    check("Latency under 5s", False, "call failed")
    check("Input tokens counted", False, "call failed")

# 3. Memory — read known fact
print(f"\n{BOLD}[3] Memory Behavior{RESET}")
try:
    r = call_claude("What AI model handles the proactive gate?")
    text = get_text(r).lower()
    tools = get_tool_calls(r)
    check("Answers with Ollama/CodeLlama", "ollama" in text or "codellama" in text, f"got: {text[:80]}")
    check("Does NOT call update_project_memory",
          not any(t.function.name == "update_project_memory" for t in tools),
          "memory updated on a read-only question")
    forbidden = ["according to", "based on your", "i can see", "looking at"]
    found = [p for p in forbidden if p in text]
    check("No forbidden phrases", len(found) == 0, f"found: {found}")
except Exception as e:
    check("Memory read test", False, str(e))

# 4. Memory — thinking aloud must NOT trigger
try:
    r = call_claude("I'm thinking maybe we should switch to PostgreSQL")
    tools = get_tool_calls(r)
    called = [t.function.name for t in tools]
    check("Thinking aloud does NOT trigger update_project_memory",
          "update_project_memory" not in called, f"tools called: {called}")
except Exception as e:
    check("Thinking aloud test", False, str(e))

# 5. Memory — explicit commit MUST trigger
try:
    r = call_claude("We're going with PostgreSQL for session storage, remember that")
    tools = get_tool_calls(r)
    called = [t.function.name for t in tools]
    inputs = json.dumps([json.loads(t.function.arguments) for t in tools if t.function.name == "update_project_memory"])
    check("Explicit commit triggers update_project_memory",
          "update_project_memory" in called, f"tools called: {called}")
    check("Tool input contains PostgreSQL",
          "postgresql" in inputs.lower(), f"input: {inputs[:120]}")
except Exception as e:
    check("Explicit commit test", False, str(e))

# 6. Rejected approach guard
print(f"\n{BOLD}[4] Rejected Approach Guard{RESET}")
try:
    r = call_claude("What should I use for the proactive gate — suggest an AI model?")
    text = get_text(r).lower()
    rejected = [a.lower() for a in JARVIS["rejected_approaches"]]
    found_rejected = [a for a in rejected if a in text]
    check("Does not suggest rejected approaches", len(found_rejected) == 0, f"suggested: {found_rejected}")
    check("Suggests Ollama for gate", "ollama" in text, f"got: {text[:80]}")
except Exception as e:
    check("Rejected approach guard", False, str(e))

# 7. Output format
print(f"\n{BOLD}[5] Output Format{RESET}")
try:
    r = call_claude("Give me a quick summary of what JARVIS does")
    text = get_text(r)
    openers = ["here are", "based on", "i can see", "looking at", "according to", "i see that"]
    found = [o for o in openers if text.lower().startswith(o)]
    check("No forbidden opener", len(found) == 0, f"starts with: '{text[:40]}'")
except Exception as e:
    check("Output format check", False, str(e))

# 8. Ollama connectivity
print(f"\n{BOLD}[6] Ollama (local mode){RESET}")
ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
try:
    resp = requests.get(f"{ollama_endpoint}/api/tags", timeout=3)
    models = [m["name"] for m in resp.json().get("models", [])]
    has_codellama = any("codellama" in m for m in models)
    check("Ollama is running", resp.status_code == 200)
    check(f"CodeLlama available {DIM}({models}){RESET}", has_codellama, "run: ollama pull codellama")
except requests.exceptions.ConnectionError:
    skip("Ollama is running", "not started — run: ollama serve")
    skip("CodeLlama available", "Ollama not running")
except Exception as e:
    skip("Ollama connectivity", str(e))

# 9. Gate prompt JSON
print(f"\n{BOLD}[7] Gate Prompt JSON{RESET}")
GATE = """Respond with ONLY a JSON object. No explanation. No code blocks. No markdown. Just JSON.

{"should_surface": true or false, "confidence": 0.0 to 1.0, "reason": "one sentence max"}

File changed: src/main.py
Last surfaced: 15 minutes ago
Current focus: Proactive developer intelligence — zero search paradigm

JSON:"""

try:
    resp = requests.post(
        f"{ollama_endpoint}/api/generate",
        json={"model": "codellama", "prompt": GATE, "stream": False},
        timeout=30
    )
    raw = resp.json().get("response", "")
    parsed = parse_ollama_json(raw)
    check("Gate returns valid JSON",
          "should_surface" in parsed and "confidence" in parsed, f"raw: {raw[:80]}")
    check("Confidence is 0-1",
          0.0 <= parsed.get("confidence", -1) <= 1.0, f"got: {parsed.get('confidence')}")
    check("Reason field present", bool(parsed.get("reason")), f"got: {parsed.get('reason')}")
    print(f"  {DIM}should_surface={parsed.get('should_surface')} | confidence={parsed.get('confidence')} | {parsed.get('reason','')[:50]}{RESET}")
except requests.exceptions.ConnectionError:
    skip("Gate JSON test", "Ollama not running")
except Exception as e:
    check("Gate prompt test", False, str(e))

# Summary
print(f"\n{BOLD}=== Results ==={RESET}")
print(f"  Passed:  \033[92m{results['passed']}\033[0m")
print(f"  Failed:  \033[91m{results['failed']}\033[0m")
if results["skipped"]:
    print(f"  Skipped: \033[93m{results['skipped']}\033[0m  (Ollama not running — expected during cloud-only dev)")

if results["failed"] == 0:
    print(f"\n  \033[92m{BOLD}All tests pass — ready to proceed.\033[0m\n")
else:
    print(f"\n  \033[91m{BOLD}{results['failed']} test(s) failing — fix before proceeding.\033[0m")
    print(f"  {DIM}Common fixes:")
    print(f"  -> memory on read question: tighten trigger words in system prompt")
    print(f"  -> no memory on commit:     add trigger phrase to tool description")
    print(f"  -> forbidden opener:        add negative constraint to behavior_rules{RESET}\n")
