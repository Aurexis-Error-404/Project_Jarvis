"""R-2 regression: truncated tool results must be valid JSON.

Covers JARVIS_IMPLEMENTATION_PLAN.md §13.0 R-2. Before the fix, results
exceeding MAX_TOOL_OUTPUT_CHARS were concatenated with '..."}' producing
malformed JSON. After the fix, the dispatcher emits a proper truncation
envelope that parses cleanly.
"""

import asyncio
import json
import sys
import types

import pytest


def _install_openai_stub():
    """The module imports openai at top-level; stub it so the test is offline-safe."""
    if "openai" in sys.modules:
        return
    stub = types.ModuleType("openai")

    class _AsyncOpenAI:
        def __init__(self, *a, **kw): ...

    stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = stub


_install_openai_stub()

from backend.ai import claude_client  # noqa: E402


class _FakeFn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, tc_id, name, arguments):
        self.id = tc_id
        self.function = _FakeFn(name, arguments)


@pytest.mark.asyncio
async def test_truncated_tool_result_is_valid_json(monkeypatch):
    """A tool result that exceeds MAX_TOOL_OUTPUT_CHARS is returned as a
    well-formed JSON envelope with truncated=True, not a busted string."""
    huge = {"files": ["f" + str(i) for i in range(5000)]}  # serializes to >> 12k chars

    async def fake_dispatch(name, inputs):
        return huge

    monkeypatch.setattr(claude_client, "dispatch_tool", fake_dispatch)

    sent = []

    async def send_event(payload):
        sent.append(payload)

    messages = []
    tc = _FakeToolCall("call_1", "read_codebase", json.dumps({"path": "."}))

    await claude_client._execute_tool(tc, messages, send_event)

    assert messages, "tool message was not appended"
    content = messages[-1]["content"]
    assert len(content) > 0

    parsed = json.loads(content)  # must not raise
    assert parsed.get("truncated") is True
    assert "partial_data" in parsed
    assert "note" in parsed
    assert parsed.get("original_size", 0) > claude_client.MAX_TOOL_OUTPUT_CHARS


@pytest.mark.asyncio
async def test_small_tool_result_passes_through_unchanged(monkeypatch):
    """Results under the limit are serialized as-is — no truncation envelope."""
    small = {"ok": True, "count": 3}

    async def fake_dispatch(name, inputs):
        return small

    monkeypatch.setattr(claude_client, "dispatch_tool", fake_dispatch)

    sent = []

    async def send_event(payload):
        sent.append(payload)

    messages = []
    tc = _FakeToolCall("call_2", "read_codebase", "{}")

    await claude_client._execute_tool(tc, messages, send_event)

    parsed = json.loads(messages[-1]["content"])
    assert parsed == small
    assert "truncated" not in parsed


@pytest.mark.asyncio
async def test_low_quality_retry_skipped_when_tools_fired(monkeypatch):
    """P1 regression: if the first pass invoked any tool, the quality-retry
    path must NOT re-enter the tool loop — non-idempotent tools (report
    generation, memory updates, automation) would double-fire."""
    calls = {"tool_loop": 0, "retry": 0}

    async def fake_run_tool_loop(messages, task_type, mode, params,
                                 send_event, allow_tools=True):
        calls["tool_loop"] += 1
        return "terse", 1  # tools fired

    async def fake_maybe_retry(**kwargs):
        calls["retry"] += 1
        return kwargs["response_text"]

    monkeypatch.setattr(claude_client, "_run_tool_loop", fake_run_tool_loop)
    monkeypatch.setattr(claude_client, "_maybe_retry_low_quality", fake_maybe_retry)
    monkeypatch.setattr(claude_client, "should_orchestrate",
                        lambda q: None, raising=False)
    from backend.ai import orchestrator as _orch
    monkeypatch.setattr(_orch, "should_orchestrate", lambda q: None)
    monkeypatch.setattr(claude_client, "_format_session_history", lambda: "")
    monkeypatch.setattr(claude_client, "load_prompt_context",
                        lambda project_path=None: {})
    monkeypatch.setattr(claude_client, "post_query_hook",
                        lambda **kw: None)

    async def send_event(_p): pass

    out = await claude_client.run(
        query="make a report", mode="cloud", send_event=send_event,
        codebase_map="x", history=[],
    )

    assert out == "terse"
    assert calls["tool_loop"] == 1
    assert calls["retry"] == 0, "retry must be skipped when tools fired"


@pytest.mark.asyncio
async def test_low_quality_retry_runs_text_only_when_no_tools(monkeypatch):
    """When the first pass fired zero tools, the retry is allowed —
    but it must run with tools disabled so we never go from text-only →
    surprise side effect."""
    captured = {}

    async def fake_run_tool_loop(messages, task_type, mode, params,
                                 send_event, allow_tools=True):
        # First call = original pass (text-only, low quality).
        # Second call = retry — record its allow_tools arg.
        if "first_done" not in captured:
            captured["first_done"] = True
            return "short", 0
        captured["retry_allow_tools"] = allow_tools
        return "better", 0

    monkeypatch.setattr(claude_client, "_run_tool_loop", fake_run_tool_loop)
    # Force low-quality verdict so the retry path is taken.
    monkeypatch.setattr(claude_client, "score_response",
                        lambda q, r: 0.0)
    monkeypatch.setattr(claude_client, "LOW_QUALITY_THRESHOLD", 0.5)
    from backend.ai import orchestrator as _orch
    monkeypatch.setattr(_orch, "should_orchestrate", lambda q: None)
    monkeypatch.setattr(claude_client, "_format_session_history", lambda: "")
    monkeypatch.setattr(claude_client, "load_prompt_context",
                        lambda project_path=None: {})
    monkeypatch.setattr(claude_client, "post_query_hook",
                        lambda **kw: None)

    async def send_event(_p): pass

    out = await claude_client.run(
        query="what is 2+2", mode="cloud", send_event=send_event,
        codebase_map="x", history=[],
    )

    assert out == "better"
    assert captured["retry_allow_tools"] is False, (
        "retry must disable tools to avoid surprise side effects"
    )


if __name__ == "__main__":
    asyncio.run(test_truncated_tool_result_is_valid_json.__wrapped__(
        monkeypatch=type("M", (), {"setattr": lambda *a, **k: None})()
    ))
