"""
AI tool-use loop — routes through providers.py (Gemini / Groq / Ollama).

Critical rules (violations cause 400 errors or silent failures):
  - tool_call_id ALWAYS from tc.id — NEVER construct it manually
  - Pass tools on EVERY API call in the loop, not just the first
  - Tools ALWAYS return dict — never raise exceptions out of a tool
  - Each tool result is its OWN "tool" role message — never bundle into one "user" message
  - Assistant message with tool_calls MUST be appended to history before tool results
"""

import datetime
import json as _json
import logging
import os

from openai import AsyncOpenAI

from backend.ai import prompts
from backend.ai.providers import PROVIDERS, get_provider, get_fallback
from backend.tools import OAI_TOOL_SCHEMAS
from backend.tools.tool_dispatcher import dispatch_tool

logger = logging.getLogger("jarvis.claude")

MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "10"))

# Cached AsyncOpenAI clients — one per provider, created on first use
_clients: dict[str, AsyncOpenAI] = {}


def _get_client(provider_name: str) -> AsyncOpenAI:
    if provider_name not in _clients:
        p = PROVIDERS[provider_name]
        _clients[provider_name] = AsyncOpenAI(
            api_key=p["api_key"], base_url=p["base_url"]
        )
    return _clients[provider_name]


async def _call_provider(provider_name: str, messages: list, tools: list = None):
    """Call a single provider. Raises on failure."""
    p = PROVIDERS[provider_name]
    client = _get_client(provider_name)
    return await client.chat.completions.create(
        model=p["model"],
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        max_tokens=4096,
        temperature=0.3,
    )


async def _call_with_fallback(
    task_type: str,
    mode: str,
    messages: list,
    tools: list = None,
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
            response = await _call_provider(name, messages, tools)
            if name != provider_name:
                logger.info(f"Used fallback provider: {name} (primary was {provider_name})")
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


async def run(query: str, mode: str, send_event,
              codebase_map: str = "Codebase not yet read. Call read_codebase('.') to load.") -> str:
    """
    Main entry point — runs the full tool-use loop for a user query.

    query: user message text
    mode: "local" | "cloud"
    send_event: async callable that sends a WebSocket event dict to the client
    """
    system = prompts.build_system_prompt(codebase_map=codebase_map)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]

    # Determine task type from mode — local always quick_qa through Ollama
    task_type = "quick_qa"
    logger.info(f"Running query (mode={mode}, task={task_type}): {query[:80]}")

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await _call_with_fallback(
                task_type=task_type,
                mode=mode,
                messages=messages,
                tools=OAI_TOOL_SCHEMAS,
            )
        except RuntimeError as e:
            logger.error(str(e))
            await send_event({"event": "jarvis_error", "message": str(e), "recoverable": False})
            return f"API error: {e}"

        choice = response.choices[0]

        if choice.finish_reason == "stop":
            text = choice.message.content or ""
            await send_event(
                {
                    "event": "jarvis_response",
                    "text": text,
                    "timestamp": _utcnow(),
                }
            )
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
                tool_input = _json.loads(tc.function.arguments)

                await send_event(
                    {"event": "tool_call_status", "tool": tool_name, "status": "start"}
                )

                result = await dispatch_tool(tool_name, tool_input)

                await send_event(
                    {
                        "event": "tool_call_status",
                        "tool": tool_name,
                        "status": "done",
                        "result_summary": str(result)[:120],
                    }
                )

                # CRITICAL: each result is its own "tool" role message
                # CRITICAL: always use tc.id — never construct tool_call_id manually
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
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
