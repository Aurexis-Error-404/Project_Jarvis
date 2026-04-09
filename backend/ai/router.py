"""
AI model router — maps mode + task_type to the correct model.
See prompts/model.md for the full routing decision table.

Routing rules (locked — do not change without AI Lead approval):
  - proactive gate → always Ollama/CodeLlama (free, local, runs 50+/hour)
  - error diagnosis → claude-sonnet (deep reasoning, user-facing quality)
  - summaries, commit messages → claude-haiku (structured output, 4x cheaper)
  - local/secure mode → ollama/codellama (zero bytes leave machine)
"""

import logging
import os

logger = logging.getLogger("jarvis.router")

_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

_CLOUD_ROUTING = {
    "research_report": _GEMINI_MODEL,     # deep reasoning → Gemini (was sonnet)
    "error_diagnosis": _GEMINI_MODEL,     # deep reasoning → Gemini (was sonnet)
    "git_summary":     _GROQ_MODEL,       # fast/cheap     → Groq   (was haiku)
    "commit_message":  _GROQ_MODEL,
    "session_summary": _GROQ_MODEL,
    "quick_qa":        _GROQ_MODEL,
    "proactive_gate":  "ollama/codellama",  # never use cloud for gate — unchanged
}


def get_model(mode: str = None, task_type: str = "quick_qa") -> str:
    """
    Returns the model string for a given mode and task type.

    mode: "local" | "cloud" | None (falls back to AI_MODE env var)
    task_type: one of the keys in _CLOUD_ROUTING
    """
    ai_mode = mode or os.environ.get("AI_MODE", "local")

    if ai_mode == "local":
        logger.debug(f"Routing to local Ollama (mode=local, task={task_type})")
        return "ollama/codellama"

    model = _CLOUD_ROUTING.get(task_type, _GROQ_MODEL)
    logger.debug(f"Routing to cloud model {model} (task={task_type})")
    return model
