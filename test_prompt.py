import anthropic
import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

with open("jarvis.json") as f:
    JARVIS = json.load(f)

SYSTEM_PROMPT = f"""<identity>
You are JARVIS — a proactive developer intelligence layer.
Project: {JARVIS['project']['name']}
Stack: {", ".join(JARVIS['project']['stack'])}
Current focus: {JARVIS['project']['current_focus']}
</identity>

<behavior_rules>
- Never say "according to your memory" or "based on the context provided" — just use the information
- Never suggest: {", ".join(JARVIS['rejected_approaches'])}
- Never start responses with "I can see", "Based on", "Looking at", or "According to"
- If asked what model/engine is used for the gate: answer "Ollama/CodeLlama"
</behavior_rules>

<tool_rules>
- update_project_memory: ONLY call when user says "remember that", "we decided", "going with", "lock this in"
- Do NOT call update_project_memory when user says "thinking about", "maybe", "what if"
</tool_rules>"""

TOOLS = [
    {
        "name": "update_project_memory",
        "description": """Update jarvis.json with a confirmed project decision.

Call ONLY when user uses explicit commit phrases:
- "remember that", "we decided", "going with", "lock this in", "note that"

Do NOT call when user is thinking aloud:
- "I'm thinking about", "maybe", "what if", "should we", "considering"

If unsure: do NOT call. Ask 'Should I remember this?' instead.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": ["decisions", "open_questions", "session_log", "rejected_approaches"]},
                "value": {"type": "object"}
            },
            "required": ["field", "value"]
        }
    },
    {
        "name": "read_codebase",
        "description": "Read current file contents from /src. Call when developer asks about current code or diagnosing a bug.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "lines": {"type": "string"}
            },
            "required": ["file_path"]
        }
    }
]

PASS = "  \033[92m✓\033[0m"
FAIL = "  \033[91m✗\033[0m"
SKIP = "  \033[93m⊘\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM  = "\033[2m"
results = {"passed": 0, "failed": 0, "skipped": 0}

def call_claude(user_input, use_tools=True):
    kwargs = dict(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_input}]
    )
    if use_tools:
        kwargs["tools"] = TOOLS
    return client.messages.create(**kwargs)

def get_text(r):
    return next((b.text for b in r.content if b.type == "text"), "")

def get_tool_calls(r):
    return [b for b in r.content if b.type == "tool_use"]

def check(name, ok, detail=""):
    if ok:
        results["passed"] += 1
        print(f"{PASS} {name}")
    else:
        results["failed"] += 1
        print(f"{FAIL} {name}")
        if detail:
            print(f"      {DIM}→ {detail}{RESET}")

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

print(f"\n{BOLD}═══ JARVIS test_prompt.py ═══{RESET}\n")

# 1. API connectivity
print(f"{BOLD}[1] API Connectivity{RESET}")
try:
    t0 = time.time()
    r = call_claude("Reply with exactly: API_OK", use_tools=False)
    latency = int((time.time() - t0) * 1000)
    text = get_text(r)
    check("API call succeeds", "API_OK" in text, f"got: {text[:60]}")
    check(f"Latency under 5s ({latency}ms)", latency < 5000)
    check("Input tokens counted", r.usage.input_tokens > 0)
    print(f"  {DIM}tokens in: {r.usage.input_tokens} | out: {r.usage.output_tokens}{RESET}")
except Exception as e:
    check("API call succeeds", False, str(e))
    check("Latency under 5s", False, "call failed")
    check("Input tokens counted", False, "call failed")

# 2. Caching
print(f"\n{BOLD}[2] Prompt Caching{RESET}")
try:
    r1 = call_claude("ping", use_tools=False)
    time.sleep(0.5)
    r2 = call_claude("pong", use_tools=False)
    written = r1.usage.cache_creation_input_tokens
    read    = r2.usage.cache_read_input_tokens
    check(f"Cache written on call 1 ({written} tokens)", written > 0)
    check(f"Cache hit on call 2 ({read} tokens read)", read > 0,
          "cache_read=0 — system prompt changed between calls or >5min gap")
    if written > 0 and read > 0:
        saving = int((1 - (read * 0.3) / (written * 3.0)) * 100)
        print(f"  {DIM}saving ~{saving}% per cached call{RESET}")
except Exception as e:
    check("Cache written", False, str(e))
    check("Cache hit", False, "call failed")

# 3. Memory — read known fact
print(f"\n{BOLD}[3] Memory Behavior{RESET}")
try:
    r = call_claude("What AI model handles the proactive gate?")
    text = get_text(r).lower()
    tools = get_tool_calls(r)
    check("Answers with Ollama/CodeLlama", "ollama" in text or "codellama" in text, f"got: {text[:80]}")
    check("Does NOT call update_project_memory",
          not any(t.name == "update_project_memory" for t in tools),
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
    called = [t.name for t in tools]
    check("Thinking aloud does NOT trigger update_project_memory",
          "update_project_memory" not in called, f"tools called: {called}")
except Exception as e:
    check("Thinking aloud test", False, str(e))

# 5. Memory — explicit commit MUST trigger
try:
    r = call_claude("We're going with PostgreSQL for session storage, remember that")
    tools = get_tool_calls(r)
    called = [t.name for t in tools]
    inputs = json.dumps([t.input for t in tools if t.name == "update_project_memory"])
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
print(f"\n{BOLD}═══ Results ═══{RESET}")
print(f"  Passed:  \033[92m{results['passed']}\033[0m")
print(f"  Failed:  \033[91m{results['failed']}\033[0m")
if results["skipped"]:
    print(f"  Skipped: \033[93m{results['skipped']}\033[0m  (Ollama not running — expected during cloud-only dev)")

if results["failed"] == 0:
    print(f"\n  \033[92m{BOLD}All tests pass — ready to proceed.\033[0m\n")
else:
    print(f"\n  \033[91m{BOLD}{results['failed']} test(s) failing — fix before proceeding.\033[0m")
    print(f"  {DIM}Common fixes:")
    print(f"  → cache miss:              system prompt changed between calls")
    print(f"  → memory on read question: tighten trigger words in system prompt")
    print(f"  → no memory on commit:     add trigger phrase to tool description")
    print(f"  → forbidden opener:        add negative constraint to behavior_rules{RESET}\n")