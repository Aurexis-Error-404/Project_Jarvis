// Chapter 07 — Bonus
Context Window Management
15 minutes · Prevents silent failures
Claude has a fixed context window. When the conversation history plus system prompt exceeds it, Claude silently drops the oldest messages. You never get an error — you just get worse answers because Claude lost context. For JARVIS, this happens if you keep conversation history indefinitely.

python
Context window management for JARVIS
# Budget for JARVIS context window (200K tokens total)
SYSTEM_PROMPT_BUDGET  = 5_000   # jarvis.json + codebase map + rules
TOOL_OUTPUTS_BUDGET   = 10_000  # tool results per turn
RESPONSE_BUDGET       = 2_000   # Claude's output
HISTORY_BUDGET        = 30_000  # conversation history
# Total: ~47K — well within 200K for most sessions

# Trim conversation history if it's getting long
def trim_history(messages: list, max_tokens: int = 30_000) -> list:
    # Rough estimate: 1 token ≈ 4 characters
    total_chars = sum(len(str(m)) for m in messages)
    estimated_tokens = total_chars // 4

    while estimated_tokens > max_tokens and len(messages) > 2:
        # Remove oldest messages (keep at least last 2 turns)
        messages.pop(0)
        total_chars = sum(len(str(m)) for m in messages)
        estimated_tokens = total_chars // 4

    return messages

# For JARVIS: tool outputs are large. git diffs, file contents, web scrapes
# Truncate them BEFORE sending to Claude, not after
MAX_TOOL_OUTPUT_TOKENS = 3000  # per tool call
MAX_GIT_DIFF_LINES     = 200
MAX_FILE_CONTENT_CHARS = 8000  # ~2000 tokens per file
MAX_WEB_PAGE_CHARS     = 12000 # ~3000 tokens per page
    
// Chapter 08 — Bonus
Streaming Responses
10 minutes · Makes JARVIS feel alive
Without streaming, JARVIS waits silently for 2–5 seconds then shows the full response at once. With streaming, text appears word-by-word as Claude generates it. This makes JARVIS feel dramatically more responsive. For a demo, streaming is the difference between "it feels like a product" and "it feels like a prototype."

python
Streaming implementation for JARVIS
import anthropic

client = anthropic.Anthropic()

async def stream_response(user_query: str, websocket):
    """Stream Claude's response to Electron in real-time"""

    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_query}]
    ) as stream:

        for text in stream.text_stream:
            # Send each chunk to Electron as it arrives
            await websocket.send_json({
                "event": "jarvis_stream_chunk",
                "text": text,
                "done": False
            })

        # Signal completion
        await websocket.send_json({
            "event": "jarvis_stream_chunk",
            "text": "",
            "done": True
        })

# In Electron React — append chunks as they arrive
# useWebSocket.js:
# if (event.event === 'jarvis_stream_chunk') {
#   setCurrentResponse(prev => prev + event.text);
#   if (event.done) setCurrentResponse('');
# }

# Note: Streaming + tool_use is more complex
# Use streaming for final text responses
# Use non-streaming for the tool_use loop (easier to manage)
    
// Chapter 09 — Bonus
Temperature & Sampling
10 minutes · Understand but rarely change
Temperature controls how "creative" vs "deterministic" Claude is. Range is 0–1. Default is around 0.7.

At temperature 0: Claude almost always gives the same answer to the same question. Good for: JSON output, commit messages, structured data. Bad for: creative writing.

At temperature 1: Claude varies more. Good for: brainstorming, creative tasks. Bad for: anything where consistency matters.

python
When to change temperature for JARVIS
# For JARVIS — most calls should use LOW temperature
# You want consistent, reliable outputs, not creative ones

client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=500,

    # Proactive gate — needs consistent JSON → temperature 0
    temperature=0,  # deterministic JSON output

    messages=[...]
)

# Error diagnosis → temperature 0 (want the same diagnosis every time)
# Session summary → temperature 0 (want consistent bullet format)
# Commit messages → temperature 0 (want consistent conventional commit format)
# Research report → temperature 0.3 (slight variation in writing style is OK)

# Honest truth: for JARVIS you will never need temperature above 0.5
# The default (no temperature specified) is ~0.7 which is fine for most cases
# Only explicitly set it to 0 for JSON-outputting prompts (proactive gate)
    
// Chapter 10 — Bonus
Common Failure Modes
15 minutes · Prevent before they happen
These are the exact failures you will hit during the 3-day build. Knowing them in advance means you fix them in 5 minutes instead of 2 hours.

text
10 failures — cause, symptom, fix
FAILURE 1: Claude stops calling tools mid-conversation
Symptom: First query works, second query gives generic answer with no tool calls
Cause:   Tool definitions are in the first API call but not subsequent ones
Fix:     Always pass tools=tool_definitions in EVERY call in the loop

FAILURE 2: tool_use_id mismatch API error
Symptom: API returns 400 error on the tool_result message
Cause:   You're constructing the ID instead of using block.id directly
Fix:     tool_result["tool_use_id"] = block.id — always from the response object

FAILURE 3: Proactive gate fires on every file save
Symptom: UI flooded with surface cards, thousands of API/Ollama calls
Cause:   Missing debounce, or debounce timer resets on every event
Fix:     Debounce: cancel previous timer before starting new one (5-second window)

FAILURE 4: Research report is generic (doesn't mention EfficientNet-B3)
Symptom: Report recommends ResNet, VGG, generic "SOTA" models
Cause:   jarvis.json context not injected into report generation prompt
Fix:     Add explicit instruction: "Recommendations MUST reference the project's
         current stack and prior decisions from the project_context above"

FAILURE 5: Claude says "I cannot access your files" or "I don't have that information"
Symptom: Claude refuses to answer questions it should know from tools
Cause:   Tool description doesn't trigger for this query type
Fix:     Test the specific query, check if tool_use fires, refine tool description

FAILURE 6: Context_surface event doesn't reach React UI
Symptom: Backend logs show event fired, nothing appears in Electron
Cause:   WebSocket event goes to Electron main process, not forwarded via IPC
Fix:     In main.js: mainWindow.webContents.send('context_surface', data)
         In React: ipcRenderer.on('context_surface', handler)

FAILURE 7: API rate limit at exactly the wrong moment
Symptom: 429 error during demo or integration test
Cause:   Multiple team members hitting API simultaneously, Tier 1 limits
Fix:     Exponential backoff (already in your code), stagger team tests,
         warm up with a test call 2 minutes before demo

FAILURE 8: Prompt cache not working — full price every call
Symptom: cache_read_input_tokens = 0 on second call
Cause:   System prompt content changed (dynamic timestamp, session data in cached section)
Fix:     Keep cached section static, move dynamic content to uncached second system block

FAILURE 9: Ollama JSON parse fails silently
Symptom: Proactive engine never surfaces anything, no errors logged
Cause:   Ollama returns JSON wrapped in ```json``` fences, parse fails,
         defaults to should_surface: false
Fix:     Use the robust parse_ollama_json() function from Chapter 6

FAILURE 10: Memory update loop — Claude updates memory repeatedly
Symptom: jarvis.json has 50 entries after one conversation
Cause:   update_project_memory tool description too broad, fires on casual statements
Fix:     Add negative examples to tool description and positive trigger words list
    
The meta-lesson: Every failure above has the same root cause — the code and the prompt are out of sync. Either the code returns something the prompt doesn't expect, or the prompt triggers behavior the code doesn't handle. The integration Lead's pipeline tests catch these. Run them every 3 hours. Fix them when they appear. Don't let them compound.