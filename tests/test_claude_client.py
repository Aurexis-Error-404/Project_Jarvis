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


if __name__ == "__main__":
    asyncio.run(test_truncated_tool_result_is_valid_json.__wrapped__(
        monkeypatch=type("M", (), {"setattr": lambda *a, **k: None})()
    ))
