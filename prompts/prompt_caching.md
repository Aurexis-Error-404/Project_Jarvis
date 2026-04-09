# prompt_caching.md — Caching Strategy for Gemini + Groq

## Status: Anthropic cache_control removed

The previous `cache_control: {"type": "ephemeral"}` block was Anthropic-specific.
Gemini via the OpenAI compatibility layer does NOT expose explicit prompt caching.
Groq has no prompt caching. This file documents what replaced it.

---

## What Gemini Does Automatically

Gemini performs automatic context caching server-side when:
- The system prompt prefix is identical across calls (byte-for-byte)
- Calls are made within a short window (~minutes)

You do not control it — you benefit from it by keeping the system prompt stable.

**Rule: never mutate the static portion of the system prompt between calls.**

```python
# ✓ CORRECT — static rules are built once at startup, never rebuilt per call
STATIC_SYSTEM_PROMPT = build_static_prompt()   # built once at module load

def call_ai(user_input: str, jarvis_json_path: str) -> str:
    dynamic = build_dynamic_context(jarvis_json_path)   # rebuilt each call (fine)
    system  = STATIC_SYSTEM_PROMPT + "\n\n" + dynamic   # static prefix stays identical
    ...
```

```python
# ✗ WRONG — rebuilding the static block per call breaks any internal caching
def call_ai(user_input: str) -> str:
    system = build_static_prompt() + "\n\n" + build_dynamic_context()
    # build_static_prompt() called every time → output identical but Gemini can't know that
```

---

## What Breaks Caching

```python
# ✗ BREAKS — timestamp in static section changes every call
STATIC = f"System built at: {datetime.now()}\n\nYou are JARVIS..."

# ✓ KEEPS — timestamp only in dynamic section (already not cached)
dynamic = f"Session started: {datetime.now()}\n\n<project_context>..."
```

---

## Demo Warm-Up (still applies)

Gemini's automatic caching warms up after the first call. Before a live demo:

```python
# Make one warm-up call 30 seconds before presenting
client.chat.completions.create(
    model="gemini-2.5-flash",
    max_tokens=10,
    messages=[
        {"role": "system", "content": STATIC_SYSTEM_PROMPT + "\n\n" + build_dynamic_context()},
        {"role": "user", "content": "ready"}
    ]
)
# Demo calls after this will be faster
```

---

## Token Budget (unchanged)

```
System prompt budget: 5,000 tokens total
  - static (identity + tool rules):  1,500 tokens  ← keep stable
  - dynamic (project context):        1,500 tokens  ← rebuilt each call
  - codebase_map:                     1,500 tokens  ← injected at session start
  - recent_sessions:                    500 tokens  ← injected at session start
```

Check tokens with:
```python
print(f"prompt_tokens: {response.usage.prompt_tokens}")
# Target: under 5,000
```
