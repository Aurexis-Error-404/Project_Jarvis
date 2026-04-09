## The Core Mental Model

Wrong model routing is either wasting money (using sonnet for something haiku handles equally well) or degrading quality (using haiku or Ollama for something that needs sonnet's reasoning depth). The routing decision is yours as AI Lead — nobody else can make it because it requires understanding both the task requirements and the model capabilities.


def get_model(task_type: str, ai_mode: str) -> str:
    if ai_mode == "local":
        return "ollama/qwen3.5:cloud"  # secure mode — everything local

    # Cloud mode routing — choose based on task
    routing = {
        # GEMINI: complex synthesis, multi-source reasoning (primary cloud)
        "research_report":    "gemini-2.5-flash",          # 8000 tokens in, complex output
        "excel_analysis":     "gemini-2.5-flash",          # data interpretation needs depth
        "error_diagnosis":    "gemini-2.5-flash",          # needs deep reasoning to find root cause

        # GROQ/LLAMA: structured tasks, short outputs, ultra-low latency
        "git_summary":        "llama-3.3-70b-versatile",   # runs every session start
        "commit_message":     "llama-3.3-70b-versatile",   # 300 tokens output max
        "session_summary":    "llama-3.3-70b-versatile",   # 5 bullets, runs on every close
        "pr_description":     "llama-3.3-70b-versatile",   # structured, short
        "quick_qa":           "llama-3.3-70b-versatile",   # short answer, fast response expected

        # OLLAMA: always-on background tasks, never user-facing quality
        "proactive_gate":     "ollama/qwen3.5:cloud",   # runs 50+ times/hour, must be free
        "relevance_scoring":  "ollama/qwen3.5:cloud",   # background signal filtering
    }
    return routing.get(task_type, "llama-3.3-70b-versatile")  # default to Groq

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
| **Gemini 2.5 Flash** | Deep reasoning, large context, multimodal | Error diagnosis, research, multi-step analysis | ~$0.15/MTok input |
| **Groq Llama-3.3-70B** | Ultra-low latency, structured output, fast | Summaries, commit messages, quick Q&A | ~$0.59/MTok input |
| **Ollama Qwen2.5-Coder** | Free, private, code-specialized | Background tasks, high-volume, non-user-facing | $0.00/MTok (compute cost only) |

**Key Insight:** The "why" is about matching the right tool to the job. You don't use a sledgehammer to crack a nut — and you don't use Sonnet for 50-times-per-hour background tasks. Cost savings come from using Haiku for structured tasks and Ollama for background processing, reserving Sonnet for when its reasoning actually matters.


# Run same query through both models — compare outputs
query = "Summarize what I worked on in the last 24 hours based on git history: [paste git log]"

results = {}
for model in ["gemini-2.5-flash", "llama-3.3-70b-versatile"]:
    response = client.chat.completions.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": query}]
    )
    results[model] = response.choices[0].message.content

# For git_summary task: Groq output should be nearly identical to Gemini
# If Groq output is significantly worse for this task → upgrade to Gemini
# If Groq output is similar → keep Groq (lower latency, cheaper)
print("Gemini:", results["gemini-2.5-flash"][:300])
print("\nGroq:",  results["llama-3.3-70b-versatile"][:300])
# Decision: if you can't tell the difference → use Groq

