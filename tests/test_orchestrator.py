"""Tests for the §4 parallel orchestrator.

Covers:
- Router respects the PARALLEL_AGENTS_ENABLED flag (off → None).
- Variant generation returns ≥2 distinct queries.
- fan_out_research survives one failing sub-agent (degraded result, no raise).
- Recursion guard: sub-agents receive `_is_sub_agent=True`.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.ai import orchestrator


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


async def _collect(events, payload):
    events.append(payload)


# ─── Routing / flag gate ──────────────────────────────────────────────────

def test_router_off_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(orchestrator, "PARALLEL_AGENTS_ENABLED", False)
    assert orchestrator.should_orchestrate("research and compare X vs Y") is None


def test_router_fan_out_signal(monkeypatch):
    monkeypatch.setattr(orchestrator, "PARALLEL_AGENTS_ENABLED", True)
    got = orchestrator.should_orchestrate("Please research and compare postgres vs sqlite tradeoffs")
    assert got == "fan_out_research"


def test_router_consensus_signal(monkeypatch):
    monkeypatch.setattr(orchestrator, "PARALLEL_AGENTS_ENABLED", True)
    got = orchestrator.should_orchestrate("why is the build failing on CI")
    assert got == "consensus_diagnosis"


def test_router_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(orchestrator, "PARALLEL_AGENTS_ENABLED", True)
    assert orchestrator.should_orchestrate("what time is it") is None


# ─── JSON variant extraction ──────────────────────────────────────────────

def test_extract_json_list_plain():
    got = orchestrator._extract_json_list('["a", "b", "c"]')
    assert got == ["a", "b", "c"]


def test_extract_json_list_fenced():
    text = '```json\n["one", "two", "three"]\n```'
    got = orchestrator._extract_json_list(text)
    assert got == ["one", "two", "three"]


def test_extract_json_list_embedded():
    text = 'Sure, here you go:\n["x", "y", "z"]\nhope that helps'
    got = orchestrator._extract_json_list(text)
    assert got == ["x", "y", "z"]


def test_extract_json_list_malformed_returns_none():
    assert orchestrator._extract_json_list("no json here") is None


# ─── Variant generation ───────────────────────────────────────────────────

def test_generate_variants_returns_three_distinct():
    payload = json.dumps(["angle one", "angle two", "angle three"])
    with patch(
        "backend.ai.claude_client._call_with_fallback",
        new=AsyncMock(return_value=_FakeResponse(payload)),
    ):
        got = asyncio.run(orchestrator._generate_variants("original", mode="cloud", n=3))
    assert len(got) == 3
    assert len(set(got)) >= 2  # must be distinct


def test_generate_variants_pads_when_model_returns_fewer():
    payload = json.dumps(["only one"])
    with patch(
        "backend.ai.claude_client._call_with_fallback",
        new=AsyncMock(return_value=_FakeResponse(payload)),
    ):
        got = asyncio.run(orchestrator._generate_variants("original", mode="cloud", n=3))
    assert len(got) == 3
    assert got[0] == "only one"


def test_generate_variants_falls_back_on_bad_json():
    with patch(
        "backend.ai.claude_client._call_with_fallback",
        new=AsyncMock(return_value=_FakeResponse("garbage response")),
    ):
        got = asyncio.run(orchestrator._generate_variants("original", mode="cloud", n=3))
    # Falls back to repeating the original query.
    assert got == ["original", "original", "original"]


# ─── Fan-out with a degraded sub-agent ────────────────────────────────────

def test_fan_out_survives_one_failing_sub_agent():
    call_count = {"n": 0}

    async def fake_sub_agent(query, mode, project_path):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return f"answer for {query}"

    events: list[dict] = []
    variants_payload = json.dumps(["q1", "q2", "q3"])

    async def go():
        with patch(
            "backend.ai.claude_client._call_with_fallback",
            new=AsyncMock(return_value=_FakeResponse(variants_payload)),
        ), patch.object(orchestrator, "_run_sub_agent", side_effect=fake_sub_agent), \
             patch.object(orchestrator, "_synthesize",
                          new=AsyncMock(return_value="merged answer")):
            result = await orchestrator.fan_out_research(
                "research and compare X vs Y",
                mode="cloud",
                send_event=lambda p: _collect(events, p),
            )
        return result

    result = asyncio.run(go())
    assert result == "merged answer"
    # Three sub-agent invocations attempted, one failed, merge still ran.
    assert call_count["n"] == 3
    phases = [e.get("phase") for e in events]
    assert "variants" in phases and "synthesizing" in phases


def test_run_sub_agent_passes_is_sub_agent_flag():
    captured = {}

    async def fake_claude_run(**kwargs):
        captured.update(kwargs)
        return "sub answer"

    async def go():
        with patch("backend.ai.claude_client.run", new=fake_claude_run):
            return await orchestrator._run_sub_agent("q", "cloud", "/some/path")

    result = asyncio.run(go())
    assert result == "sub answer"
    assert captured.get("_is_sub_agent") is True
    assert captured.get("project_path") == "/some/path"
