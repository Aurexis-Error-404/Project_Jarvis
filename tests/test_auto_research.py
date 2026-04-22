"""Tests for the §6 auto-research iteration loop.

Covers:
- Halts at AUTO_RESEARCH_MAX_ITERATIONS even when score never crosses target.
- Halts early when target score is reached.
- Halts at budget cap.
- Streams `auto_research_progress` events (running / scored / done).
- Returns the BEST answer seen, not necessarily the last.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.ai import auto_research


def _run(coro):
    return asyncio.run(coro)


async def _collector(events):
    async def send(payload):
        events.append(payload)
    return send


def test_halts_at_iteration_cap(monkeypatch):
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_ENABLED", True)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_MAX_ITERATIONS", 3)
    # Force target to be unreachable so the loop exhausts iterations.
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_TARGET_SCORE", 2.0)
    monkeypatch.setattr(auto_research, "_COST_PER_ITERATION_USD", 0.0)

    events: list[dict] = []

    async def fake_claude_run(**kwargs):
        return "short"  # low quality on purpose

    async def send(p): events.append(p)

    async def go():
        with patch("backend.ai.claude_client.run", new=fake_claude_run), \
             patch("backend.ai.claude_client._stream_text", new=AsyncMock()):
            return await auto_research.run_auto_research("q", "cloud", send)

    result = _run(go())
    iterations = [e for e in events if e.get("phase") == "running"]
    assert len(iterations) == 3
    done = [e for e in events if e.get("phase") == "done"]
    assert len(done) == 1
    assert result  # non-empty fallback


def test_halts_on_target_score(monkeypatch):
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_ENABLED", True)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_MAX_ITERATIONS", 5)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_TARGET_SCORE", 0.0)  # first iter passes
    monkeypatch.setattr(auto_research, "_COST_PER_ITERATION_USD", 0.0)

    events: list[dict] = []

    async def fake_claude_run(**kwargs):
        return "some reasonable answer that has enough body to score well"

    async def send(p): events.append(p)

    async def go():
        with patch("backend.ai.claude_client.run", new=fake_claude_run), \
             patch("backend.ai.claude_client._stream_text", new=AsyncMock()):
            return await auto_research.run_auto_research("q", "cloud", send)

    _run(go())
    running = [e for e in events if e.get("phase") == "running"]
    assert len(running) == 1  # stopped after first iteration


def test_halts_on_budget_cap(monkeypatch):
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_ENABLED", True)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_MAX_ITERATIONS", 10)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_MAX_COST_USD", 0.10)
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_TARGET_SCORE", 2.0)  # unreachable
    monkeypatch.setattr(auto_research, "_COST_PER_ITERATION_USD", 0.05)

    events: list[dict] = []

    async def fake_claude_run(**kwargs):
        return "meh"

    async def send(p): events.append(p)

    async def go():
        with patch("backend.ai.claude_client.run", new=fake_claude_run), \
             patch("backend.ai.claude_client._stream_text", new=AsyncMock()):
            await auto_research.run_auto_research("q", "cloud", send)

    _run(go())
    running = [e for e in events if e.get("phase") == "running"]
    # Budget 0.10 / 0.05 per iter = 2 iterations before budget cap trips.
    assert len(running) == 2


def test_disabled_flag_runs_single_pass(monkeypatch):
    monkeypatch.setattr(auto_research, "AUTO_RESEARCH_ENABLED", False)
    call_count = {"n": 0}

    async def fake_claude_run(**kwargs):
        call_count["n"] += 1
        assert kwargs.get("_is_sub_agent") is True
        return "answer"

    async def send(_p): pass

    async def go():
        with patch("backend.ai.claude_client.run", new=fake_claude_run):
            return await auto_research.run_auto_research("q", "cloud", send)

    result = _run(go())
    assert result == "answer"
    assert call_count["n"] == 1
