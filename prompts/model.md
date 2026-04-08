## The Core Mental Model

Wrong model routing is either wasting money (using sonnet for something haiku handles equally well) or degrading quality (using haiku or Ollama for something that needs sonnet's reasoning depth). The routing decision is yours as AI Lead — nobody else can make it because it requires understanding both the task requirements and the model capabilities.


def get_model(task_type: str, ai_mode: str) -> str:
    if ai_mode == "local":
        return "ollama/codellama"  # secure mode — everything local

    # Cloud mode routing — choose based on task
    routing = {
        # SONNET: complex synthesis, multi-source reasoning
        "research_report":    "claude-sonnet-4-20250514",  # 8000 tokens in, complex output
        "excel_analysis":     "claude-sonnet-4-20250514",  # data interpretation needs depth
        "error_diagnosis":    "claude-sonnet-4-20250514",  # needs deep reasoning to find root cause

        # HAIKU: structured tasks, short outputs, repetitive calls
        "git_summary":        "claude-haiku-4-5-20251001",  # runs every session start
        "commit_message":     "claude-haiku-4-5-20251001",  # 300 tokens output max
        "session_summary":    "claude-haiku-4-5-20251001",  # 5 bullets, runs on every close
        "pr_description":     "claude-haiku-4-5-20251001",  # structured, short
        "quick_qa":           "claude-haiku-4-5-20251001",  # short answer, fast response expected

        # OLLAMA: always-on background tasks, never user-facing quality
        "proactive_gate":     "ollama/codellama",  # runs 50+ times/hour, must be free
        "relevance_scoring":  "ollama/codellama",  # background signal filtering
    }
    return routing.get(task_type, "claude-haiku-4-5-20251001")  # default to haiku

# The key insight: proactive_gate runs in background, never user-facing
# The gate output (true/false JSON) doesn't need sonnet-level reasoning
# error_diagnosis IS user-facing quality and needs the best model


## The Ollama JSON problem

import json, re

def parse_ollama_json(raw: str) -> dict:
    """
    Handles all the ways Ollama fails to return clean JSON:
    1. ```json ... ``` markdown fences
    2. ``` ... ``` plain fences
    3. Extra text before/after the JSON
    4. Single quotes instead of double quotes
    """

    # Step 1: Strip markdown code fences
    raw = re.sub(r'```(?:json)?\n?', '', raw)
    raw = raw.replace('```', '')

    # Step 2: Find the JSON object (handles text before/after)
    match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if not match:
        return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}

    json_str = match.group()

    # Step 3: Try parsing
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Step 4: Try fixing single quotes (common Ollama mistake)
        try:
            fixed = json_str.replace("'", '"')
            return json.loads(fixed)
        except:
            return {"should_surface": False, "confidence": 0.0, "reason": "parse failed"}

# Also: Ollama prompts should be more aggressive about JSON-only output
OLLAMA_GATE_PROMPT = """Respond with ONLY a JSON object. No other text.
No explanation. No code blocks. No markdown. Just the JSON:

{"should_surface": true, "confidence": 0.8, "reason": "one sentence"}

Signal: {signal_type} — {file_path}
Project focus: {current_focus}

JSON:"""  # "JSON:" at the end primes Ollama to start with {


## The "Why" Behind the Model Choice

| Model | Strengths | When to Use | Cost |
|-------|-----------|-------------|------|
| **Claude Sonnet** | Deep reasoning, complex synthesis, large context | Error diagnosis, research, multi-step analysis | $3.00/MTok input |
| **Claude Haiku** | Fast, structured output, repetitive tasks | Summaries, commit messages, quick Q&A | $0.25/MTok input |
| **Ollama (local)** | Free, private, always available | Background tasks, high-volume, non-user-facing | $0.00/MTok (compute cost only) |

**Key Insight:** The "why" is about matching the right tool to the job. You don't use a sledgehammer to crack a nut — and you don't use Sonnet for 50-times-per-hour background tasks. Cost savings come from using Haiku for structured tasks and Ollama for background processing, reserving Sonnet for when its reasoning actually matters.


# Run same query through all three models — compare outputs
query = "Summarize what I worked on in the last 24 hours based on git history: [paste git log]"

results = {}
for model in ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]:
    response = client.messages.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": query}]
    )
    results[model] = response.content[0].text

# For git_summary task: haiku output should be nearly identical to sonnet
# If haiku output is significantly worse for this task → upgrade to sonnet
# If haiku output is similar → keep haiku (4x cheaper, faster)
print("Sonnet:", results["claude-sonnet-4-20250514"][:300])
print("\nHaiku:",  results["claude-haiku-4-5-20251001"][:300])
# Decision: if you can't tell the difference → use haiku

