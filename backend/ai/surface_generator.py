"""
surface_generator.py — Generates proactive context card bullets via Groq (cloud)
or Ollama (local/secure mode).

Called from file_watcher._evaluate() after the Ollama gate passes.
Reuses _call_with_fallback() from claude_client so the full provider chain
and logging are inherited automatically.

Task routing (from providers.py):
  "proactive_surface" in cloud mode → groq
  "proactive_surface" in local mode → ollama
"""

import asyncio
import functools
import logging

from backend.ai.claude_client import _call_with_fallback
from backend.memory.jarvis_json import read as read_jarvis
from backend.tools.git_interface import run as git_run

logger = logging.getLogger("jarvis.surface_generator")

SURFACE_PROMPT_TEMPLATE = """You are generating a proactive context card for a developer.

Project context:
- Current focus: {current_focus}
- Stack: {stack}
- Recent decisions: {recent_decisions}

File signal:
- File changed: {file_path}
- Recent git activity on this file: {git_summary}

Generate exactly 2-3 bullet points. Rules:
- Each bullet: maximum 15 words
- Every bullet must reference a specific function name, variable, line number, or commit detail
- Do NOT write generic advice
- Do NOT start with "You" or "Consider" or "Remember"
- If you have nothing project-specific to say: return empty string

Format: return ONLY the bullets, one per line, starting with \u2022
No preamble, no explanation, no heading."""


def _format_git_summary(git_result: dict) -> str:
    """Compact git summary for the surface prompt — cap at ~300 chars."""
    commits = git_result.get("commits", [])
    if not commits:
        return "No recent git activity on this file."
    lines = []
    for c in commits[:5]:
        sha = c.get("sha", "?")
        msg = c.get("message", "").split("\n")[0][:80]
        author = c.get("author", "?").split("<")[0].strip()
        lines.append(f"  {sha} {author}: {msg}")
    return "\n".join(lines)


async def generate(file_path: str, gate_reason: str, mode: str) -> list:
    """
    Generate 2-3 project-specific surface card bullets for a changed file.

    Returns a list of bullet strings (each starts with •), or [] if generation
    fails or the model returns nothing project-specific.
    """
    jarvis = read_jarvis()
    project = jarvis.get("project", {})
    current_focus = project.get("current_focus", "Not specified")
    stack = ", ".join(project.get("stack", []))
    decisions = jarvis.get("decisions", [])
    recent_decisions = "; ".join(
        f"{d['what']}: chose {d['chose']}" for d in decisions[:3]
    ) or "None yet."

    # git_run is sync/CPU-bound — run in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    git_result = await loop.run_in_executor(
        None, functools.partial(git_run, since="24h", include_diff=False, file_path=file_path)
    )
    git_summary = _format_git_summary(git_result)

    prompt = SURFACE_PROMPT_TEMPLATE.format(
        current_focus=current_focus,
        stack=stack,
        recent_decisions=recent_decisions,
        file_path=file_path.replace("\\", "/"),
        git_summary=git_summary,
    )

    try:
        response = await _call_with_fallback(
            task_type="proactive_surface",
            mode=mode,
            messages=[{"role": "user", "content": prompt}],
            tools=None,
        )
        raw_text = response.choices[0].message.content or ""
    except RuntimeError as e:
        logger.error(f"surface_generator provider error for {file_path}: {e}")
        return []

    bullets = [
        line.strip()
        for line in raw_text.splitlines()
        if line.strip().startswith("\u2022")
    ]

    if not bullets:
        logger.warning(
            f"Surface generator returned no bullets for {file_path}. "
            f"Raw: {raw_text[:120]}"
        )

    return bullets[:3]
