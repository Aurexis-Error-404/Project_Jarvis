"""Auto-research loop — iterative refinement until quality threshold met.

§6 of JARVIS_IMPLEMENTATION_PLAN.md:
  * Runs a sub-agent, scores its answer, and if below threshold re-queries
    with a refined prompt. Halts on iteration cap or budget cap.

Safety rails:
  * **Off by default.** `AUTO_RESEARCH_ENABLED=1` opts in.
  * **Never auto-starts.** Only invoked when the user explicitly asks
    ("research this deeply", "keep going until you get a good answer",
    or an explicit tool call). Routing lives in the caller, not here.
  * Hard caps: `AUTO_RESEARCH_MAX_ITERATIONS` (default 5) and
    `AUTO_RESEARCH_MAX_COST_USD` (default 0.25).
  * Streams `auto_research_progress` events so the UI can show an
    abort-able progress card.
  * Sub-agents use `_is_sub_agent=True` — no recursive orchestrator.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Final

from backend.ai.quality import LOW_QUALITY_THRESHOLD, score_response

logger = logging.getLogger("jarvis.auto_research")

AUTO_RESEARCH_ENABLED: bool = os.environ.get("AUTO_RESEARCH_ENABLED", "0").lower() in (
    "1", "true", "yes",
)
AUTO_RESEARCH_MAX_ITERATIONS: Final[int] = int(
    os.environ.get("AUTO_RESEARCH_MAX_ITERATIONS", "5")
)
AUTO_RESEARCH_MAX_COST_USD: Final[float] = float(
    os.environ.get("AUTO_RESEARCH_MAX_COST_USD", "0.25")
)
# Stop when score is "good enough" — a bit above the retry threshold so
# we don't burn iterations chasing marginal gains.
AUTO_RESEARCH_TARGET_SCORE: Final[float] = max(0.75, LOW_QUALITY_THRESHOLD + 0.2)

# Rough per-iteration cost estimate. Real cost accounting would need
# token usage from each provider call; this is a conservative placeholder
# so the budget cap is enforced even without token metering.
_COST_PER_ITERATION_USD: Final[float] = 0.05


def _refinement_prompt(original: str, prior_answer: str, prior_score: float) -> str:
    """Build the user message for the next iteration."""
    return (
        f"Original question: {original}\n\n"
        f"A prior attempt scored {prior_score:.2f}/1.0 and was judged insufficient. "
        "Previous answer (for context only — do not repeat it verbatim):\n"
        f"---\n{prior_answer[:2000]}\n---\n\n"
        "Produce a materially better answer. Use different sources or angles, "
        "add concrete numbers, cite specifics, and avoid the gaps in the prior attempt."
    )


async def run_auto_research(
    query: str,
    mode: str,
    send_event,
    project_path: str | None = None,
) -> str:
    """Iterate until the answer is good enough or a cap trips.

    Returns the best answer seen across all iterations (not necessarily
    the last one). Never raises — caps and errors yield a degraded but
    usable final string.
    """
    from backend.ai.claude_client import run as claude_run

    if not AUTO_RESEARCH_ENABLED:
        # Defensive — caller should gate, but never silently iterate.
        return await claude_run(
            query=query, mode=mode, send_event=send_event,
            project_path=project_path, _is_sub_agent=True,
        )

    started = time.monotonic()
    best_answer = ""
    best_score = -1.0
    current_query = query
    prior_answer = ""

    for iteration in range(1, AUTO_RESEARCH_MAX_ITERATIONS + 1):
        spent_usd = _COST_PER_ITERATION_USD * (iteration - 1)
        if spent_usd >= AUTO_RESEARCH_MAX_COST_USD:
            logger.info(f"auto_research budget cap hit at iter {iteration}")
            break

        await send_event({
            "event": "auto_research_progress",
            "iteration": iteration,
            "total": AUTO_RESEARCH_MAX_ITERATIONS,
            "best_score": round(best_score, 2) if best_score >= 0 else None,
            "spent_usd": round(spent_usd, 3),
            "phase": "running",
        })

        try:
            answer = await claude_run(
                query=current_query,
                mode=mode,
                send_event=send_event if iteration == AUTO_RESEARCH_MAX_ITERATIONS else _silent,
                project_path=project_path,
                _is_sub_agent=True,
            )
        except Exception as e:
            logger.warning(f"auto_research iter {iteration} failed: {e}")
            continue

        score = score_response(query, answer)
        logger.info(f"auto_research iter {iteration}: score={score:.2f}")

        await send_event({
            "event": "auto_research_progress",
            "iteration": iteration,
            "total": AUTO_RESEARCH_MAX_ITERATIONS,
            "current_score": round(score, 2),
            "best_score": round(max(best_score, score), 2),
            "spent_usd": round(spent_usd + _COST_PER_ITERATION_USD, 3),
            "phase": "scored",
        })

        if score > best_score:
            best_score = score
            best_answer = answer

        if score >= AUTO_RESEARCH_TARGET_SCORE:
            logger.info(f"auto_research target reached at iter {iteration}")
            break

        prior_answer = answer
        current_query = _refinement_prompt(query, prior_answer, score)

    elapsed = time.monotonic() - started
    await send_event({
        "event": "auto_research_progress",
        "phase": "done",
        "best_score": round(best_score, 2) if best_score >= 0 else None,
        "elapsed_s": round(elapsed, 1),
    })

    if not best_answer:
        return "(auto-research produced no usable answer within the iteration/budget caps)"

    # Stream the final selected answer so the UI shows the winning result,
    # not whichever iteration happened to stream last.
    from backend.ai.claude_client import _stream_text
    await _stream_text(best_answer, send_event)
    return best_answer


async def _silent(_payload: dict) -> None:
    pass
