"""Parallel and pipeline orchestration strategies.

§4 of JARVIS_IMPLEMENTATION_PLAN.md:
  * `fan_out_research` — 3 variant sub-queries in parallel, then a merge.
  * `consensus_diagnosis` — 3 parallel diagnosis attempts, merged by
    majority + synthesis.
  * `pipeline_query` — classify → deep → format, sequential.

Safety rails:
  * Off by default. `PARALLEL_AGENTS_ENABLED=1` opts in.
  * `asyncio.gather(..., return_exceptions=True)` — a failing sub-agent
    yields a degraded result, never a top-level crash.
  * Sub-agents stream **nothing** to the UI (`send_event=_noop`). Only
    the merge phase streams. Avoids three overlapping `jarvis_stream_chunk`
    floods in the renderer.
  * Concurrent provider calls are bounded by `PROVIDER_HEALTH.slot(name)`
    in `_call_with_fallback`, so fan-out does not exceed Gemini's 15 RPM
    free tier.
  * Recursion guard: orchestrator calls the core tool loop directly via
    `claude_client.run(..., _is_sub_agent=True)`, which skips orchestrator
    routing on the inner call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

logger = logging.getLogger("jarvis.orchestrator")

PARALLEL_AGENTS_ENABLED: bool = os.environ.get("PARALLEL_AGENTS_ENABLED", "0").lower() in (
    "1", "true", "yes",
)


_VARIANT_SYSTEM = (
    "You are a query-splitting assistant. Given one research question, "
    "produce exactly THREE distinct sub-queries that together cover the topic "
    "from different angles. Each sub-query must be directly searchable on the "
    "web and must not be a near-duplicate of the others. Return a JSON list "
    "of three strings. No prose, no markdown, no explanation."
)

_SYNTH_SYSTEM_RESEARCH = (
    "You are a research synthesizer. You are given the user's original "
    "question and three independent answers from sub-agents. Produce ONE "
    "cohesive answer that:\n"
    "- cites each sub-agent's distinct contribution\n"
    "- reconciles disagreements explicitly\n"
    "- avoids duplicating text verbatim\n"
    "- preserves concrete numbers, benchmarks, and citations"
)

_SYNTH_SYSTEM_DIAGNOSIS = (
    "You are a diagnosis synthesizer. You are given three independent "
    "diagnoses of the same problem. Extract the most likely CAUSE "
    "(the one most agents agree on, or the best-supported if they "
    "disagree), the recommended FIX, and a short ALSO CHECK list. "
    "Output plain text with the sections CAUSE:, FIX:, ALSO CHECK: each "
    "on their own line."
)


async def _noop(_payload: dict) -> None:
    pass


def _extract_json_list(text: str) -> list[str] | None:
    """Pull the first JSON list of strings out of a possibly-noisy reply."""
    if not text:
        return None
    # First try direct json.loads.
    stripped = text.strip()
    if stripped.startswith("```"):
        # Strip markdown fences like ```json ... ```
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    try:
        val = json.loads(stripped)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            return val
    except (ValueError, json.JSONDecodeError):
        pass
    # Fallback: first [...] block.
    m = re.search(r"\[[^\[\]]*\]", text, re.DOTALL)
    if m:
        try:
            val = json.loads(m.group(0))
            if isinstance(val, list) and all(isinstance(x, str) for x in val):
                return val
        except (ValueError, json.JSONDecodeError):
            return None
    return None


async def _generate_variants(query: str, mode: str, n: int = 3) -> list[str]:
    """One LLM call that returns n distinct sub-queries."""
    from backend.ai.claude_client import _call_with_fallback

    try:
        response = await _call_with_fallback(
            task_type="quick_qa",
            mode=mode,
            messages=[
                {"role": "system", "content": _VARIANT_SYSTEM},
                {"role": "user", "content": query},
            ],
            tools=None,
            temperature=0.7,
            max_tokens=512,
        )
        text = response.choices[0].message.content or ""
        parsed = _extract_json_list(text)
        if parsed:
            # Deduplicate while preserving order, then pad with the original
            # query if the model gave us fewer distinct variants than asked.
            seen: set[str] = set()
            deduped: list[str] = []
            for v in parsed:
                k = v.strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    deduped.append(v.strip())
            if deduped:
                while len(deduped) < n:
                    deduped.append(query)
                return deduped[:n]
    except Exception as e:
        logger.warning(f"variant generation failed: {e}")
    # Fallback: repeat the query (parallel runs still produce independent
    # tool calls and word-choices even on identical input).
    return [query] * n


async def _run_sub_agent(query: str, mode: str, project_path: str | None) -> str:
    """A single sub-agent invocation. Silent — no frontend events.

    Uses `_is_sub_agent=True` so the inner `run()` does not re-enter
    orchestrator routing.
    """
    from backend.ai.claude_client import run as claude_run

    try:
        return await claude_run(
            query=query,
            mode=mode,
            send_event=_noop,
            project_path=project_path,
            _is_sub_agent=True,
        )
    except Exception as e:
        logger.warning(f"sub-agent failed on query={query[:60]!r}: {e}")
        return ""


async def _synthesize(
    *,
    system_prompt: str,
    user_content: str,
    mode: str,
    send_event,
    task_type: str = "research_report",
    max_tokens: int = 4096,
) -> str:
    """Final merge call — streams to the UI."""
    from backend.ai.claude_client import _stream_final_response, _stream_text

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    if mode == "cloud":
        streamed = await _stream_final_response(task_type, mode, messages, send_event)
        if streamed is not None:
            return streamed

    from backend.ai.claude_client import _call_with_fallback

    response = await _call_with_fallback(
        task_type=task_type,
        mode=mode,
        messages=messages,
        tools=None,
        temperature=0.4,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content or ""
    await _stream_text(text, send_event)
    return text


def _format_subagent_results(query: str, variants: list[str], results: list[str]) -> str:
    chunks = [f"Original question: {query}\n"]
    for i, (variant, res) in enumerate(zip(variants, results), start=1):
        body = res.strip() if res else "(sub-agent returned no content)"
        chunks.append(f"--- Sub-agent {i} (variant: {variant!r}) ---\n{body}")
    return "\n\n".join(chunks)


# ─── Strategies ──────────────────────────────────────────────────────────

async def fan_out_research(
    query: str,
    mode: str,
    send_event,
    project_path: str | None = None,
) -> str:
    """Split a research query into 3 angles, run them in parallel, synthesize."""
    await send_event({"event": "orchestrator_status", "strategy": "fan_out_research",
                      "phase": "variants", "iteration": 0, "total": 3})
    variants = await _generate_variants(query, mode, n=3)
    logger.info(f"fan_out_research variants: {variants}")

    await send_event({"event": "orchestrator_status", "strategy": "fan_out_research",
                      "phase": "running", "iteration": 0, "total": len(variants)})

    results = await asyncio.gather(
        *(_run_sub_agent(v, mode, project_path) for v in variants),
        return_exceptions=True,
    )
    # `return_exceptions=True` puts BaseException instances in the list — map
    # them to empty strings so `_format_subagent_results` sees only str.
    cleaned: list[str] = []
    for r in results:
        if isinstance(r, str):
            cleaned.append(r)
        else:
            logger.warning(f"sub-agent raised: {r!r}")
            cleaned.append("")

    await send_event({"event": "orchestrator_status", "strategy": "fan_out_research",
                      "phase": "synthesizing"})

    user_content = _format_subagent_results(query, variants, cleaned)
    return await _synthesize(
        system_prompt=_SYNTH_SYSTEM_RESEARCH,
        user_content=user_content,
        mode=mode,
        send_event=send_event,
    )


async def consensus_diagnosis(
    query: str,
    mode: str,
    send_event,
    project_path: str | None = None,
) -> str:
    """Run three independent diagnoses, then synthesize a CAUSE/FIX consensus."""
    await send_event({"event": "orchestrator_status", "strategy": "consensus_diagnosis",
                      "phase": "running", "iteration": 0, "total": 3})

    # Same query repeated — providers vary on phrasing & tool choice and the
    # three answers diverge meaningfully on non-trivial bugs.
    results = await asyncio.gather(
        *(_run_sub_agent(query, mode, project_path) for _ in range(3)),
        return_exceptions=True,
    )
    cleaned = [r if isinstance(r, str) else "" for r in results]

    await send_event({"event": "orchestrator_status", "strategy": "consensus_diagnosis",
                      "phase": "synthesizing"})

    user_content = _format_subagent_results(query, [query, query, query], cleaned)
    return await _synthesize(
        system_prompt=_SYNTH_SYSTEM_DIAGNOSIS,
        user_content=user_content,
        mode=mode,
        send_event=send_event,
        task_type="error_diagnosis",
        max_tokens=2048,
    )


async def pipeline_query(
    query: str,
    mode: str,
    send_event,
    project_path: str | None = None,
) -> str:
    """Sequential classify → deep → format. Cheaper than fan-out for
    queries where parallel exploration adds no value."""
    await send_event({"event": "orchestrator_status", "strategy": "pipeline_query",
                      "phase": "classify"})
    classification = await _run_sub_agent(
        f"Classify this in one word (bug | research | howto | other): {query}",
        mode, project_path,
    )

    await send_event({"event": "orchestrator_status", "strategy": "pipeline_query",
                      "phase": "deep"})
    deep = await _run_sub_agent(query, mode, project_path)

    await send_event({"event": "orchestrator_status", "strategy": "pipeline_query",
                      "phase": "format"})
    return await _synthesize(
        system_prompt=(
            "You are a formatter. Given a classification hint and a deep "
            "answer, return the deep answer cleaned up (fix structure, "
            "remove filler, keep all technical content)."
        ),
        user_content=f"Classification: {classification.strip()[:40]}\n\nDeep answer:\n{deep}",
        mode=mode,
        send_event=send_event,
        task_type="quick_qa",
        max_tokens=2048,
    )


# ─── Routing ─────────────────────────────────────────────────────────────

# Conservative: require both a research verb and a comparative signal.
_FAN_OUT_SIGNALS = re.compile(
    r"(?i)\b(research|investigate|survey|benchmark|review)\b.*\b(compare|versus|vs\.?|alternatives?|options?|trade[- ]?offs?)\b",
)
_CONSENSUS_SIGNALS = re.compile(
    r"(?i)(why\s+is\s+.+\s+(failing|broken|crashing)|diagnose\s+the|root\s+cause|why\s+does\s+.+\s+not\s+work)",
)


def should_orchestrate(query: str) -> str | None:
    """Return the strategy name to use, or None to stay single-agent."""
    if not PARALLEL_AGENTS_ENABLED:
        return None
    if not query:
        return None
    if _FAN_OUT_SIGNALS.search(query):
        return "fan_out_research"
    if _CONSENSUS_SIGNALS.search(query):
        return "consensus_diagnosis"
    return None


async def route(
    strategy: str,
    *,
    query: str,
    mode: str,
    send_event,
    project_path: str | None = None,
) -> str:
    if strategy == "fan_out_research":
        return await fan_out_research(query, mode, send_event, project_path)
    if strategy == "consensus_diagnosis":
        return await consensus_diagnosis(query, mode, send_event, project_path)
    if strategy == "pipeline_query":
        return await pipeline_query(query, mode, send_event, project_path)
    raise ValueError(f"Unknown orchestrator strategy: {strategy}")
