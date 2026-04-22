"""Heuristic response-quality scorer.

Design rules — see JARVIS_IMPLEMENTATION_PLAN.md §8:
- Heuristic only. No LLM call. Target runtime: under 20 ms on a 4k-char
  response.
- Returns a score in [0.0, 1.0]. Scores below `LOW_QUALITY_THRESHOLD`
  (0.5) trigger a one-shot retry in `claude_client.run` — never inside
  the tool loop, and never more than once.
- Scoring is deliberately conservative: only penalize patterns that are
  strong signals of a broken answer. False positives cost the user an
  extra API call; false negatives are acceptable.

Signals considered:
  * Length — very short replies to non-trivial prompts are usually a
    punt ("I don't know", "Sorry, I can't help").
  * Refusal / apology openings — catch the common refusal preambles.
  * Error-passthrough — raw tracebacks or provider error strings that
    leaked into the assistant message.
  * Repetition — the model looped on the same phrase.
  * Structure — presence of code fences / bullets for queries that
    clearly want structured output (bonus, never a penalty).
"""

from __future__ import annotations

import re
from typing import Final

LOW_QUALITY_THRESHOLD: Final[float] = 0.5

_REFUSAL_PATTERNS = re.compile(
    r"(?i)^\s*(i\s*(?:am|'m)?\s*sorry|i\s*(?:cannot|can't|won't)|i\s*don['\u2019]t\s+know|"
    r"unfortunately[, ]|as an ai|i\s*apologi[sz]e)",
)

_ERROR_PASSTHROUGH = re.compile(
    r"(?i)(traceback\s*\(most recent call last\)|"
    r"openai\.|litellm\.|rate[_\s-]?limit(?:ed)?|429\s+too many|"
    r"500\s+internal|\"error\"\s*:)",
)

_LIST_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+\.)\s+", re.MULTILINE)
_CODE_FENCE = re.compile(r"```")


def _repetition_ratio(text: str) -> float:
    """Ratio of the most common 5-gram across the response. High = loopy."""
    tokens = text.split()
    if len(tokens) < 20:
        return 0.0
    grams: dict[tuple, int] = {}
    for i in range(len(tokens) - 4):
        key = tuple(tokens[i : i + 5])
        grams[key] = grams.get(key, 0) + 1
    if not grams:
        return 0.0
    most = max(grams.values())
    return most / max(1, len(tokens) - 4)


def _structure_bonus(query: str, response: str) -> float:
    """Small bonus when structured output is clearly warranted."""
    q_lower = query.lower()
    wants_structure = any(
        kw in q_lower
        for kw in ("list ", "steps", "compare", "summarize", "bullet", "report")
    )
    if not wants_structure:
        return 0.0
    has_bullets = bool(_LIST_BULLET.search(response))
    has_code = bool(_CODE_FENCE.search(response))
    if has_bullets or has_code:
        return 0.1
    return 0.0


def score_response(query: str, response: str) -> float:
    """Score an assistant response in [0.0, 1.0].

    A score of 1.0 means no red flags fired; scores approach 0.0 as more
    penalties compound. `query` is needed only to contextualize the length
    and structure heuristics.
    """
    if not isinstance(response, str) or not response.strip():
        return 0.0

    text = response.strip()
    length = len(text)
    query_len = len(query or "")

    score = 1.0

    # Short-response penalty — a very short reply to any non-trivial prompt
    # is almost always a punt. Harsher penalty when the response is nearly
    # empty, so "ok." and "I don't know." don't squeak past the threshold.
    if length < 20:
        score -= 0.6
    elif query_len > 40 and length < 80:
        score -= 0.4

    if _REFUSAL_PATTERNS.search(text[:200]):
        score -= 0.3

    if _ERROR_PASSTHROUGH.search(text):
        score -= 0.55

    rep = _repetition_ratio(text)
    if rep > 0.08:
        score -= min(0.6, rep * 2)

    score += _structure_bonus(query or "", text)

    return max(0.0, min(1.0, score))


def is_low_quality(query: str, response: str) -> bool:
    """Convenience wrapper — returns True if the score is below threshold."""
    return score_response(query, response) < LOW_QUALITY_THRESHOLD
