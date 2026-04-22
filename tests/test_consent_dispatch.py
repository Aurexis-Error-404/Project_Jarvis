"""Integration test: tool_dispatcher gates consent-required tools."""

from __future__ import annotations

import asyncio

import pytest

from backend.tools import tool_dispatcher


class _FakeConsent:
    def __init__(self, decision: bool):
        self.decision = decision
        self.calls: list[tuple[str, dict]] = []

    async def request(self, action: str, payload: dict) -> bool:
        self.calls.append((action, payload))
        return self.decision


def test_denial_shortcircuits(monkeypatch):
    mgr = _FakeConsent(decision=False)
    result = asyncio.run(tool_dispatcher.dispatch_tool(
        "computer_automation",
        {"action": "click", "x": 10, "y": 10},
        consent_manager=mgr,
    ))
    assert result.get("error") == "user denied consent"
    assert mgr.calls == [("computer_automation", {"action": "click", "x": 10, "y": 10})]


def test_missing_consent_manager_denies(monkeypatch):
    # ContextVar default is None, and no explicit manager given.
    result = asyncio.run(tool_dispatcher.dispatch_tool(
        "computer_automation",
        {"action": "screenshot"},
        consent_manager=None,
    ))
    assert "error" in result
    assert "consent required" in result["error"]


def test_non_gated_tool_bypasses_consent():
    # read_codebase is not gated — consent_manager untouched.
    mgr = _FakeConsent(decision=False)
    result = asyncio.run(tool_dispatcher.dispatch_tool(
        "read_codebase",
        {"file_path": "."},
        consent_manager=mgr,
    ))
    assert mgr.calls == []
    # The actual read may succeed or return a structured error — either is fine.
    assert isinstance(result, dict)


def test_approval_dispatches_tool(monkeypatch):
    mgr = _FakeConsent(decision=True)

    # Stub the computer_automation implementation so the test does not
    # require pyautogui to be installed.
    def fake_run(**kwargs):
        return {"ok": True, "received": kwargs}

    monkeypatch.setitem(tool_dispatcher._SYNC_TOOLS, "computer_automation", fake_run)

    result = asyncio.run(tool_dispatcher.dispatch_tool(
        "computer_automation",
        {"action": "screenshot"},
        consent_manager=mgr,
    ))
    assert result.get("ok") is True
    assert mgr.calls and mgr.calls[0][0] == "computer_automation"
