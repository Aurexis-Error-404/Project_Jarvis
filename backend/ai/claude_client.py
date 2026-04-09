"""
AI tool-use loop — Gemini (primary) + Groq (fallback) via OpenAI-compatible endpoints.

Critical rules (violations cause 400 errors or silent failures):
  - tool_call_id ALWAYS from tc.id — NEVER construct it manually
  - Pass tools=OAI_TOOL_SCHEMAS on EVERY API call, not just the first
  - Tools ALWAYS return dict — never raise exceptions out of a tool
  - Each tool result is its OWN "tool" role message — never bundle into one "user" message
  - Assistant message with tool_calls MUST be appended to history before tool results
"""

import datetime
import json as _json
import logging
import os
import time

from openai import OpenAI

from backend.ai import prompts
from backend.tools import OAI_TOOL_SCHEMAS
from backend.tools.tool_dispatcher import dispatch_tool

logger = logging.getLogger("jarvis.claude")

_gemini_client = OpenAI(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

_groq_client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1",
)

MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "10"))


async def run(query: str, mode: str, send_event) -> str:
    """
    Main entry point — runs the full tool-use loop for a user query.

    query: user message text
    mode: "local" | "cloud"
    send_event: async callable that sends a WebSocket event dict to the client
    """
    system = prompts.build_system_prompt()  # returns str
    messages = [{"role": "user", "content": query}]

    if mode == "local":
        from backend.ai import ollama_client
        text = await ollama_client.chat(prompt=query, system=system)
        await send_event({"event": "jarvis_reply", "text": text, "timestamp": _utcnow()})
        return text

    logger.info(f"Running query (mode={mode}): {query[:80]}")

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = _call_cloud(system=system, messages=messages)
        except Exception as e:
            logger.error(f"All AI providers failed: {e}")
            await send_event({"event": "error", "message": str(e), "recoverable": False})
            return f"API error: {e}"

        choice = response.choices[0]

        if choice.finish_reason == "stop":
            text = choice.message.content or ""
            await send_event(
                {
                    "event": "jarvis_reply",
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

                # CRITICAL: each tool result is its own "tool" role message
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

        # Unexpected finish reason
        logger.warning(f"Unexpected finish_reason: {choice.finish_reason}")
        break

    logger.warning("Max tool iterations reached")
    await send_event(
        {
            "event": "error",
            "message": "Reached max tool iterations. Please ask a more specific question.",
            "recoverable": True,
        }
    )
    return "I ran into a loop. Please try a more specific question."


def _call_cloud(system: str, messages: list):
    """
    Call Gemini first (up to 3 attempts with backoff on rate limits).
    On any non-rate-limit error, fall back to Groq immediately.
    Raises if both providers fail.
    """
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    groq_model   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    full_messages = [{"role": "system", "content": system}] + messages

    for attempt in range(3):
        try:
            resp = _gemini_client.chat.completions.create(
                model=gemini_model,
                max_tokens=2000,
                messages=full_messages,
                tools=OAI_TOOL_SCHEMAS,
                tool_choice="auto",
            )
            logger.debug("Gemini call succeeded")
            return resp
        except Exception as e:
            is_rate_limit = "429" in str(e) or "rate" in str(e).lower()
            if attempt < 2 and is_rate_limit:
                wait = 2 ** (attempt + 1)  # 2s, 4s
                logger.warning(f"Gemini rate limited — retrying in {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            logger.warning(f"Gemini failed ({e}), falling back to Groq")
            break

    # Groq fallback
    resp = _groq_client.chat.completions.create(
        model=groq_model,
        max_tokens=2000,
        messages=full_messages,
        tools=OAI_TOOL_SCHEMAS,
        tool_choice="auto",
    )
    logger.info("Groq fallback succeeded")
    return resp


def _utcnow() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"
