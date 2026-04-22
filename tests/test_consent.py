"""Tests for the §7.2 consent framework + audit log."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.ai import consent as consent_mod
from backend.ai.audit import append_audit


# ─── ConsentManager ──────────────────────────────────────────────────────

def test_denies_when_no_send_event_bound(tmp_path):
    mgr = consent_mod.ConsentManager(send_event=None, project_path=str(tmp_path))
    approved = asyncio.run(mgr.request("computer_automation", {"action": "click"}))
    assert approved is False
    # Denial is audited.
    log = (tmp_path / ".claude" / "audit.log").read_text(encoding="utf-8")
    assert "denied_no_ui" in log


def test_request_fires_event_and_resolves_on_approve(tmp_path):
    events: list[dict] = []

    async def send(payload): events.append(payload)

    mgr = consent_mod.ConsentManager(send_event=send, project_path=str(tmp_path))

    async def go():
        task = asyncio.create_task(mgr.request("computer_automation", {"action": "screenshot"}))
        # Wait a tick so the request lands in _pending.
        await asyncio.sleep(0.02)
        assert len(events) == 1
        req_id = events[0]["request_id"]
        await mgr.resolve(req_id, approved=True)
        return await task

    approved = asyncio.run(go())
    assert approved is True

    log_path = tmp_path / ".claude" / "audit.log"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["decision"] == "approved"
    assert entry["action"] == "computer_automation"


def test_request_times_out_and_is_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(consent_mod, "CONSENT_TIMEOUT_SECONDS", 0.1)

    async def send(_p): pass

    mgr = consent_mod.ConsentManager(send_event=send, project_path=str(tmp_path))
    approved = asyncio.run(mgr.request("computer_automation", {"action": "click"}))
    assert approved is False
    log = (tmp_path / ".claude" / "audit.log").read_text(encoding="utf-8")
    assert "denied" in log


def test_resolve_unknown_request_id_returns_false(tmp_path):
    mgr = consent_mod.ConsentManager(send_event=None, project_path=str(tmp_path))
    got = asyncio.run(mgr.resolve("nope", approved=True))
    assert got is False


# ─── Audit log ────────────────────────────────────────────────────────────

def test_audit_redacts_api_keys_in_payload(tmp_path):
    append_audit(
        str(tmp_path),
        action="test",
        payload={"text": "my key is AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567"},
        decision="approved",
    )
    log = (tmp_path / ".claude" / "audit.log").read_text(encoding="utf-8")
    assert "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ" not in log
    assert "REDACTED" in log


def test_audit_append_is_jsonl(tmp_path):
    append_audit(str(tmp_path), "a1", {"k": 1}, decision="approved")
    append_audit(str(tmp_path), "a2", {"k": 2}, decision="denied")
    path = tmp_path / ".claude" / "audit.log"
    lines = [json.loads(line) for line in path.read_text().strip().splitlines()]
    assert len(lines) == 2
    assert [l["action"] for l in lines] == ["a1", "a2"]


# ─── ContextVar ──────────────────────────────────────────────────────────

def test_contextvar_roundtrip(tmp_path):
    mgr = consent_mod.ConsentManager(send_event=None, project_path=str(tmp_path))
    token = consent_mod.set_active(mgr)
    try:
        assert consent_mod.current() is mgr
    finally:
        consent_mod.reset_active(token)
    assert consent_mod.current() is None
