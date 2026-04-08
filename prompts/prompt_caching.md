# Core:
Every subsequent call that uses the exact system prompt reads it from cache at 10% of the normal cost .Ex:The system prompt cost for jarvis is ~4000 tokens.with caching each call costs  $0.0012.over 100 calls $1.20 saved.


**BEFORE — full price every call
system=[{
    "type": "text",
    "text": system_prompt
}]

 **AFTER — 90% cheaper after first call
system=[{
    "type": "text",
    "text": system_prompt,
    "cache_control": {"type": "ephemeral"}  # ← this one line

}]

** "ephemeral" = 5 minute TTL (time to live)
** The cache resets if your system prompt content changes
**The cache resets after 5 minutes of no calls
**During development: very active, cache stays warm
** During the demo: warm up the cache with one test call before presenting.


How to verify caching is working — always check this:

python
Cache verification
response = client.messages.create(...)

# On first call — cache miss, you pay full price to write it
print(response.usage.cache_creation_input_tokens)  # e.g. 3800 (system prompt size)
print(response.usage.cache_read_input_tokens)       # 0

# On second call with same system prompt — cache hit!
print(response.usage.cache_creation_input_tokens)  # 0
print(response.usage.cache_read_input_tokens)       # 3800 ← reading from cache

# If cache_read is 0 on second call:
# → Your system prompt changed (even one character breaks the cache)
# → More than 5 minutes between calls
# → You forgot the cache_control field

# Cache pricing breakdown:
# Cache write: $3.75/MTok (1.25x normal — you pay a small premium to cache it)
# Cache read:  $0.30/MTok  (10% of normal — you pay almost nothing)
# Normal:      $3.00/MTok
# Break-even:  after 1.25 reads, caching is net profitable


JARVIS-specific setup: Before the hackathon demo, make one warm-up call to get the cache loaded. The demo then runs on cached system prompts. If the demo machine was idle for 5+ minutes before presenting, make another warm-up call while setting up the projector.

# ❌ BREAKS CACHE — jarvis.json timestamp changes on every load
system_prompt = f"Project: {project_name}. Last updated: {datetime.now()}"

# ✓ KEEPS CACHE — timestamp excluded from cached section
system_prompt = f"Project: {project_name}."  # no timestamp in cached content

# ❌ BREAKS CACHE — session summary changes every call
system_prompt = f"...\nSession notes: {current_session_notes}"

# ✓ KEEPS CACHE — separate static from dynamic content
# Cached static section (jarvis.json decisions, codebase map)
system=[
    {
        "type": "text",
        "text": static_context,  # never changes between calls
        "cache_control": {"type": "ephemeral"}
    },
    {
        "type": "text",
        "text": dynamic_context  # current session notes — not cached, that's fine
        # no cache_control here
    }
]