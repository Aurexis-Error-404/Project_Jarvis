"""R-3 regression: sync tools must not hang the dispatcher forever.

Covers JARVIS_IMPLEMENTATION_PLAN.md §13.0 R-3. Before the fix, sync tools
ran via run_in_executor with no timeout; a misbehaving tool would block the
agent loop indefinitely. After the fix, the dispatcher returns a structured
timeout error within TOOL_TIMEOUT_SECONDS.
"""

import time

import pytest

from backend.tools import tool_dispatcher


@pytest.mark.asyncio
async def test_sync_tool_hits_timeout(monkeypatch):
    """A sync tool whose runtime exceeds TOOL_TIMEOUT_SECONDS must produce a
    structured {'error': ...} payload, and must do so roughly at the timeout —
    not block indefinitely. We shrink the timeout to make the test fast and
    use a bounded sleep so the executor thread can't outlive the process."""
    monkeypatch.setattr(tool_dispatcher, "TOOL_TIMEOUT_SECONDS", 0.3)

    def slow(**_inputs):
        time.sleep(3.0)  # bounded, guaranteed to outlast the 0.3s timeout
        return {"never": "reached"}

    monkeypatch.setitem(tool_dispatcher._SYNC_TOOLS, "_slow", slow)

    start = time.monotonic()
    result = await tool_dispatcher.dispatch_tool("_slow", {})
    elapsed = time.monotonic() - start

    assert isinstance(result, dict)
    assert "error" in result, f"Expected error dict, got {result!r}"
    assert "timed out" in result["error"].lower()
    assert elapsed < 1.5, f"Dispatch did not short-circuit — took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_fast_sync_tool_returns_normally(monkeypatch):
    """Sanity: a sync tool that finishes quickly still goes through."""

    def quick(**inputs):
        return {"ok": True, "echo": inputs}

    monkeypatch.setitem(tool_dispatcher._SYNC_TOOLS, "_quick", quick)

    result = await tool_dispatcher.dispatch_tool("_quick", {"x": 1})
    assert result == {"ok": True, "echo": {"x": 1}}
