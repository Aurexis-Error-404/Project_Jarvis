"""
Tool dispatcher — routes Claude's tool_use blocks to the correct implementation.

Called by claude_client.py after every tool_use stop_reason.
All tools must return dict — never raise exceptions.
"""

import logging

from backend.tools import codebase_reader, git_interface, report_generator, web_research
from backend.memory import jarvis_json, session_log

logger = logging.getLogger("jarvis.dispatcher")


async def dispatch_tool(name: str, inputs: dict) -> dict:
    """
    Route a tool call to its implementation.
    Returns a dict. Never raises — wraps all exceptions as {"error": "..."}.
    """
    logger.info(f"Dispatching tool: {name} inputs={list(inputs.keys())}")

    try:
        if name == "read_codebase":
            return codebase_reader.run(**inputs)

        elif name == "read_git_history":
            return git_interface.run(**inputs)

        elif name == "web_research":
            return await web_research.run(**inputs)

        elif name == "generate_html_report":
            return report_generator.run(**inputs)

        elif name == "update_project_memory":
            return jarvis_json.update(**inputs)

        elif name == "read_session_history":
            return session_log.read(**inputs)

        else:
            logger.warning(f"Unknown tool: {name}")
            return {"error": f"Unknown tool: {name}"}

    except TypeError as e:
        # Wrong parameters passed by Claude
        logger.error(f"Tool {name} called with wrong parameters: {e}")
        return {"error": f"Parameter error in {name}: {e}"}
    except Exception as e:
        logger.exception(f"Tool {name} raised an unexpected error")
        return {"error": f"Tool {name} failed: {e}"}
