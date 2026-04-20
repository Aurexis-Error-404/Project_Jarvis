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
from backend.ai.security import redact_keys
from backend.context.workspace import Workspace, reset_active, set_active
from backend.memory.prompt_log import load_prompt_context, post_query_hook
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

def _format_session_history() -> str:
    """Read recent sessions from jarvis.json and format for the system prompt."""
    try:
        from backend.memory.session_log import read as read_sessions
        sess = read_sessions(last_n_sessions=3)
        sessions = sess.get("sessions", [])
        if not sessions:
            return "No previous sessions recorded."
        lines = []
        for s in sessions:
            ts = s.get("timestamp", "unknown time")
            msgs = s.get("messages", 0)
            mode = s.get("mode", "unknown")
            lines.append(f"- {ts}: {msgs} messages ({mode} mode)")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to load session history: {e}")
        return "Session history unavailable."


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
              history: list = None,
              project_path: str | None = None) -> str:
    """
    Main entry point — runs the full tool-use loop for a user query.

    query: user message text
    mode: "local" | "cloud"
    send_event: async callable that sends a WebSocket event dict to the client
    history: prior turns [{role, content}, ...] for session continuity
    """
    workspace_token = set_active(Workspace(project_path))
    try:
        session_summary = _format_session_history()
        prompt_context = load_prompt_context(project_path=project_path)
        system = prompts.build_system_prompt(
            codebase_map=codebase_map,
            session_history=session_summary,
            user_prefs=prompt_context.get("user_prefs", ""),
            failure_log=prompt_context.get("failure_log", ""),
            success_log=prompt_context.get("success_log", ""),
            capability_map=prompt_context.get("capability_map", ""),
        )
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})

        # Infer task type from query — drives provider routing and adaptive params
        # Local mode always uses quick_qa — Ollama works best with fast params
        # (research_report would set max_tokens=8192 which is very slow on Ollama)
        task_type = "quick_qa" if mode == "local" else _infer_task_type(query)
        params = _TASK_PARAMS.get(task_type, {"temperature": 0.4, "max_tokens": 4096})
        logger.info(f"Running query (mode={mode}, task={task_type}): {redact_keys(query[:80])}")

        # Enable tools for all modes — Ollama's OpenAI-compat endpoint supports
        # tool definitions (tool_choice handled separately in _call_provider)
        response_text = await _run_tool_loop(messages, task_type, mode, params, send_event)
        tool_calls_made = sum(1 for m in messages if m.get("role") == "tool")
        post_query_hook(
            query=query,
            response=response_text,
            tool_calls_made=tool_calls_made,
            project_path=project_path,
        )
        return response_text
    finally:
        reset_active(workspace_token)


async def _run_tool_loop(messages: list, task_type: str, mode: str,
                         params: dict, send_event) -> str:
    from backend.ai.agent import JarvisAgent

    agent = JarvisAgent(
        messages=messages,
        task_type=task_type,
        mode=mode,
        params=params,
        send_event=send_event,
        call_with_fallback=_call_with_fallback,
        stream_final_response=_stream_final_response,
        stream_text=_stream_text,
        execute_tool=_execute_tool,
        trim_history=_trim_history,
        tool_schemas=OAI_TOOL_SCHEMAS,
        max_iterations=MAX_TOOL_ITERATIONS,
    )
    return await agent.run()


async def _execute_tool(tc, messages: list, send_event,
                        pre_tool_check=None, post_tool_check=None) -> None:
    """Dispatch a single tool call and append the result to messages."""
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
        return

    if pre_tool_check is not None:
        pre_result = await pre_tool_check(tool_name, tool_input)
        if pre_result is not None:
            result = pre_result
            result_json = _json.dumps(result, ensure_ascii=False, default=str)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})
            return

    await send_event({
        "event": "tool_call_status", "tool": tool_name, "status": "start",
        "params": {k: str(v)[:80] for k, v in tool_input.items()},
    })

    tool_start = time.monotonic()
    result = await dispatch_tool(tool_name, tool_input)
    tool_elapsed = int((time.monotonic() - tool_start) * 1000)
    if post_tool_check is not None:
        result = await post_tool_check(tool_name, result)

    result_json = _json.dumps(result, ensure_ascii=False, default=str)
    if len(result_json) > MAX_TOOL_OUTPUT_CHARS:
        truncated_payload = {
            "truncated": True,
            "original_size": len(result_json),
            "partial_data": result_json[:MAX_TOOL_OUTPUT_CHARS],
            "note": (
                f"Tool result exceeded {MAX_TOOL_OUTPUT_CHARS} chars and was truncated. "
                "partial_data contains the first N chars of the serialized result; "
                "it may be partial JSON. Narrow the query or paginate to see the rest."
            ),
        }
        result_json = _json.dumps(truncated_payload, ensure_ascii=False)

    await send_event({
        "event": "tool_call_status", "tool": tool_name, "status": "done",
        "result_summary": result_json[:200], "duration_ms": tool_elapsed,
    })

    # CRITICAL: each result is its own "tool" role message
    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})

    if tool_name == "generate_html_report" and isinstance(result, dict) and "path" in result:
        await send_event({
            "event": "report_generated",
            "path": result["path"],
            "html": result.get("html", ""),
        })


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
