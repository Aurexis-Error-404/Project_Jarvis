"""
AI tool-use loop — routes through providers.py (Gemini / Groq / Ollama).

Critical rules (violations cause 400 errors or silent failures):
  - tool_call_id ALWAYS from tc.id — NEVER construct it manually
  - Pass tools on EVERY API call in the loop, not just the first
  - Tools ALWAYS return dict — never raise exceptions out of a tool
  - Each tool result is its OWN "tool" role message — never bundle into one "user" message
  - Assistant message with tool_calls MUST be appended to history before tool results
"""

import asyncio
import datetime
import json as _json
import logging
import os
import time

from openai import AsyncOpenAI

from backend.ai import prompts
from backend.ai.providers import PROVIDERS, get_provider, get_fallback
from backend.tools import OAI_TOOL_SCHEMAS
from backend.tools.tool_dispatcher import dispatch_tool

logger = logging.getLogger("jarvis.claude")

MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "10"))
HISTORY_TOKEN_BUDGET = 30_000
MAX_TOOL_OUTPUT_CHARS = 12_000


def _trim_history(messages: list) -> list:
    """Drop oldest non-system messages when history exceeds token budget."""
    total_chars = sum(len(str(m)) for m in messages)
    while total_chars // 4 > HISTORY_TOKEN_BUDGET and len(messages) > 2:
        messages.pop(1)  # keep system prompt at [0]
        total_chars = sum(len(str(m)) for m in messages)
    return messages

# Priority-ordered task inference — first match wins.
# More specific patterns come first to avoid false matches
# (e.g. "research report" must match before "error" in "error while researching")
_TASK_TYPE_RULES = [
    # Most specific multi-word patterns first
    ("research_report", ["research report", "generate report", "create report", "make a report",
                         "investigate and report", "write a report"]),
    ("commit_message",  ["commit message", "write commit", "draft commit"]),
    ("git_summary",     ["git log", "commit history", "changelog", "what changed",
                         "what did i change", "recent commits"]),
    # Then broader patterns — only if nothing specific matched
    ("research_report", ["research", "investigate", "survey", "benchmark", "compare alternatives"]),
    ("error_diagnosis", ["traceback", "exception", "stack trace", "error:", "crash",
                         "bug", "broken", "fails with", "not working", "TypeError",
                         "ValueError", "KeyError", "ImportError", "AttributeError"]),
]


def _infer_task_type(query: str) -> str:
    """Infer task_type from query content for cloud provider routing.
    Priority-ordered: first match wins. More specific patterns checked first."""
    q = query.lower()
    for task_type, keywords in _TASK_TYPE_RULES:
        if any(kw in q for kw in keywords):
            return task_type
    return "quick_qa"

# Cached AsyncOpenAI clients — one per provider, created on first use
_clients: dict[str, AsyncOpenAI] = {}


def _get_client(provider_name: str) -> AsyncOpenAI:
    if provider_name not in _clients:
        p = PROVIDERS[provider_name]
        _clients[provider_name] = AsyncOpenAI(
            api_key=p["api_key"], base_url=p["base_url"]
        )
    return _clients[provider_name]


async def _call_provider(provider_name: str, messages: list, tools: list = None,
                         temperature: float = 0.3, max_tokens: int = 4096,
                         stream: bool = False):
    """Call a single provider. Raises on failure."""
    p = PROVIDERS[provider_name]
    client = _get_client(provider_name)
    # Ollama's OpenAI-compat endpoint accepts tools but chokes on tool_choice="auto"
    tool_choice_val = "auto" if (tools and provider_name != "ollama") else None
    return await client.chat.completions.create(
        model=p["model"],
        messages=messages,
        tools=tools if tools else None,
        tool_choice=tool_choice_val,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=stream,
    )


async def _call_with_fallback(
    task_type: str,
    mode: str,
    messages: list,
    tools: list = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    stream: bool = False,
):
    """
    Routes to the correct provider for (task_type, mode) and walks the
    fallback chain on failure.  Raises RuntimeError if all providers fail.
    """
    provider_name = get_provider(task_type, mode)

    # Build the attempt chain (Gemini → Groq, or Ollama with no fallback)
    chain = []
    current = provider_name
    seen: set = set()
    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        current = get_fallback(current, mode)

    last_error = None
    for name in chain:
        p = PROVIDERS[name]

        if not p["api_key"]:
            logger.warning(f"Skipping {name} — API key not set")
            continue

        try:
            response = await _call_provider(
                name, messages, tools,
                temperature=temperature, max_tokens=max_tokens, stream=stream,
            )
            if name != provider_name:
                logger.info(f"Fallback: {provider_name} → {name} for task={task_type}")
            else:
                logger.debug(f"Provider: {name} | task: {task_type} | mode: {mode}")
            return response

        except Exception as e:
            last_error = e
            logger.warning(f"{name} failed: {e}. Trying next in chain...")
            continue

    raise RuntimeError(
        f"All providers failed for task='{task_type}' mode='{mode}'. Last error: {last_error}"
    )


async def _stream_text(text: str, send_event) -> None:
    """Send text as a series of word-level streaming chunks to the frontend."""
    if not text:
        await send_event({"event": "jarvis_stream_chunk", "text": "", "done": True})
        return

    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        await send_event(
            {"event": "jarvis_stream_chunk", "text": chunk, "done": False}
        )
        await asyncio.sleep(0.005)

    await send_event({"event": "jarvis_stream_chunk", "text": "", "done": True})


# Task-adaptive parameters — better output quality per task type
_TASK_PARAMS = {
    "error_diagnosis":  {"temperature": 0.2, "max_tokens": 4096},
    "research_report":  {"temperature": 0.5, "max_tokens": 8192},
    "git_summary":      {"temperature": 0.2, "max_tokens": 2048},
    "commit_message":   {"temperature": 0.2, "max_tokens": 1024},
    "session_summary":  {"temperature": 0.3, "max_tokens": 2048},
    "quick_qa":         {"temperature": 0.4, "max_tokens": 4096},
}


async def _stream_final_response(task_type, mode, messages, send_event):
    """Stream the final text response to the frontend using the OpenAI streaming API."""
    try:
        stream = await _call_with_fallback(
            task_type=task_type,
            mode=mode,
            messages=messages,
            tools=None,  # Final response — no tools, just text
            stream=True,
            **_TASK_PARAMS.get(task_type, {"temperature": 0.4, "max_tokens": 4096}),
        )
        full_text = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
                await send_event({
                    "event": "jarvis_stream_chunk",
                    "text": delta.content,
                    "done": False,
                })
        await send_event({"event": "jarvis_stream_chunk", "text": "", "done": True})
        return full_text
    except Exception as e:
        logger.warning(f"Streaming failed, falling back to _stream_text: {e}")
        return None  # Caller will fall back to _stream_text


async def run(query: str, mode: str, send_event,
              codebase_map: str = "Codebase not yet read. Call read_codebase('.') to load.",
              history: list = None) -> str:
    """
    Main entry point — runs the full tool-use loop for a user query.

    query: user message text
    mode: "local" | "cloud"
    send_event: async callable that sends a WebSocket event dict to the client
    history: prior turns [{role, content}, ...] for session continuity
    """
    system = prompts.build_system_prompt(codebase_map=codebase_map)
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": query})

    # Infer task type from query — drives provider routing and adaptive params
    # Local mode always uses quick_qa — Ollama works best with fast params
    # (research_report would set max_tokens=8192 which is very slow on Ollama)
    task_type = "quick_qa" if mode == "local" else _infer_task_type(query)
    params = _TASK_PARAMS.get(task_type, {"temperature": 0.4, "max_tokens": 4096})
    logger.info(f"Running query (mode={mode}, task={task_type}): {query[:80]}")

    # Enable tools for all modes — Ollama's OpenAI-compat endpoint supports
    # tool definitions (tool_choice handled separately in _call_provider)
    use_tools = OAI_TOOL_SCHEMAS

    for iteration in range(MAX_TOOL_ITERATIONS):
        _trim_history(messages)
        try:
            response = await _call_with_fallback(
                task_type=task_type,
                mode=mode,
                messages=messages,
                tools=use_tools,
                **params,
            )
        except RuntimeError as e:
            err = str(e)
            logger.error(err)
            is_ollama = "ollama" in err.lower() or "connection" in err.lower()
            await send_event({
                "event": "jarvis_error",
                "message": "Ollama is not running. Start with: ollama serve" if is_ollama else err,
                "recoverable": is_ollama,
            })
            return f"API error: {e}"

        choice = response.choices[0]

        if choice.finish_reason == "stop":
            text = choice.message.content or ""
            # Only use real streaming API for cloud mode after tool calls.
            # Ollama's stream=True can hang indefinitely (never sends [DONE]),
            # which would permanently disable the chat input.
            if iteration > 0 and mode == "cloud":
                streamed = await _stream_final_response(task_type, mode, messages, send_event)
                if streamed is not None:
                    return streamed
            await _stream_text(text, send_event)
            return text

        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls or []

            # CRITICAL: append assistant message with tool_calls to history first
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = _json.loads(tc.function.arguments)
                except (ValueError, _json.JSONDecodeError) as e:
                    logger.warning(f"Malformed tool arguments for {tool_name}: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _json.dumps({"error": f"Malformed arguments: {e}"}),
                    })
                    continue

                await send_event({
                    "event": "tool_call_status",
                    "tool": tool_name,
                    "status": "start",
                    "params": {k: str(v)[:80] for k, v in tool_input.items()},
                })

                tool_start = time.monotonic()
                result = await dispatch_tool(tool_name, tool_input)
                tool_elapsed = int((time.monotonic() - tool_start) * 1000)

                # Serialize result as clean JSON for the model (truncate large outputs)
                result_json = _json.dumps(result, ensure_ascii=False, default=str)
                if len(result_json) > MAX_TOOL_OUTPUT_CHARS:
                    result_json = result_json[:MAX_TOOL_OUTPUT_CHARS] + '..."}'

                await send_event({
                    "event": "tool_call_status",
                    "tool": tool_name,
                    "status": "done",
                    "result_summary": result_json[:200],
                    "duration_ms": tool_elapsed,
                })

                # CRITICAL: each result is its own "tool" role message
                # CRITICAL: always use tc.id — never construct tool_call_id manually
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_json,
                    }
                )

                # Special event for report generation
                if tool_name == "generate_html_report" and isinstance(result, dict) and "path" in result:
                    await send_event(
                        {
                            "event": "report_generated",
                            "path": result["path"],
                            "html": result.get("html", ""),
                        }
                    )

            continue

        logger.warning(f"Unexpected finish_reason: {choice.finish_reason}")
        break

    logger.warning("Max tool iterations reached")
    await send_event(
        {
            "event": "jarvis_error",
            "message": "Reached max tool iterations. Please ask a more specific question.",
            "recoverable": True,
        }
    )
    return "I ran into a loop. Please try a more specific question."


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
