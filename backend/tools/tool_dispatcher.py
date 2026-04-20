"""
Tool dispatcher — routes Claude's tool_use blocks to the correct implementation.

Called by claude_client.py after every tool_use stop_reason.
All tools must return dict — never raise exceptions.
"""

import asyncio
import contextvars
import functools
import logging

from backend.tools import codebase_reader, git_interface, report_generator, web_research
from backend.memory import jarvis_json, session_log

logger = logging.getLogger("jarvis.dispatcher")

# Timeout applied to BOTH sync and async tool dispatch. Overridable in tests.
TOOL_TIMEOUT_SECONDS: float = 60.0

# Sync tools — run in thread executor to avoid blocking the event loop
_SYNC_TOOLS = {
    "read_codebase":       codebase_reader.run,
    "read_git_history":    git_interface.run,
    "generate_html_report": report_generator.run,
    "update_project_memory": jarvis_json.update,
    "read_session_history": session_log.read,
}

# Async tools — awaited directly
_ASYNC_TOOLS = {
    "web_research": web_research.run,
}


async def dispatch_tool(name: str, inputs: dict) -> dict:
    """
    Route a tool call to its implementation.
    Returns a dict. Never raises — wraps all exceptions as {"error": "..."}.
    """
    logger.info(f"Dispatching tool: {name} inputs={list(inputs.keys())}")

    try:
        if name in _ASYNC_TOOLS:
            return await asyncio.wait_for(
                _ASYNC_TOOLS[name](**inputs), timeout=TOOL_TIMEOUT_SECONDS,
            )

        if name in _SYNC_TOOLS:
            loop = asyncio.get_event_loop()
            # Copy the current async context (including the active Workspace
            # ContextVar) into the executor thread so sync tools can read
            # per-session state without growing an explicit parameter.
            ctx = contextvars.copy_context()
            call = functools.partial(_SYNC_TOOLS[name], **inputs)
            fut = loop.run_in_executor(None, lambda: ctx.run(call))
            return await asyncio.wait_for(fut, timeout=TOOL_TIMEOUT_SECONDS)

        logger.warning(f"Unknown tool: {name}")
        return {"error": f"Unknown tool: {name}"}

    except asyncio.TimeoutError:
        logger.error(f"Tool {name} timed out after {TOOL_TIMEOUT_SECONDS}s")
        return {"error": f"Tool {name} timed out after {TOOL_TIMEOUT_SECONDS} seconds"}
    except TypeError as e:
        logger.error(f"Tool {name} called with wrong parameters: {e}")
        return {"error": f"Parameter error in {name}: {e}"}
    except Exception as e:
        logger.exception(f"Tool {name} raised an unexpected error")
        return {"error": f"Tool {name} failed: {e}"}
