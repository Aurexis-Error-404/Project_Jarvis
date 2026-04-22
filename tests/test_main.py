"""R-5 regression: concurrent WebSocket sessions must each own their mode.

Covers JARVIS_IMPLEMENTATION_PLAN.md §13.0 R-5 and §5.5. Before the fix,
_current_mode was a process global. If session A switched to cloud, session
B's next user_query would also run in cloud — silent cross-session leak.
After the fix, _handle_mode_change returns the new mode and the ws handler
stores it in a local variable.
"""

import sys
import types
from pathlib import Path

import pytest


def _install_openai_stub():
    if "openai" in sys.modules:
        return
    stub = types.ModuleType("openai")

    class _AsyncOpenAI:
        def __init__(self, *a, **kw): ...

    stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = stub


_install_openai_stub()

from backend import main as jarvis_main  # noqa: E402


@pytest.mark.asyncio
async def test_handle_mode_change_returns_new_mode_without_mutating_global():
    """_handle_mode_change returns the new mode for the caller to store
    locally. No module-level variable flips as a side effect."""
    events = []

    async def send_event(payload):
        events.append(payload)

    before_default = jarvis_main._default_mode

    new_mode = await jarvis_main._handle_mode_change({"mode": "cloud"}, send_event)
    assert new_mode == "cloud"
    assert jarvis_main._default_mode == before_default, (
        "_default_mode must never be mutated by a handler"
    )
    assert any(e.get("event") == "jarvis_mode_ack" and e.get("mode") == "cloud"
               for e in events)


@pytest.mark.asyncio
async def test_handle_mode_change_rejects_invalid_mode():
    errs = []

    async def send_event(payload):
        errs.append(payload)

    result = await jarvis_main._handle_mode_change({"mode": "chaos"}, send_event)
    assert result is None
    assert any(e.get("event") == "jarvis_error" for e in errs)


@pytest.mark.asyncio
async def test_concurrent_sessions_have_independent_mode(monkeypatch):
    """Simulate two ws sessions: A flips to cloud, B must still be local."""

    async def send_a(_payload):
        pass

    async def send_b(_payload):
        pass

    # Two independent local-variable worlds, like two ws_handler coroutines.
    session_a_mode = jarvis_main._default_mode  # "local"
    session_b_mode = jarvis_main._default_mode  # "local"

    new_for_a = await jarvis_main._handle_mode_change({"mode": "cloud"}, send_a)
    if new_for_a is not None:
        session_a_mode = new_for_a

    # Session B has not sent a mode_change; its local variable must still be "local".
    assert session_a_mode == "cloud"
    assert session_b_mode == "local"
    assert jarvis_main._default_mode == "local"

    # And the per-query fallback path in _handle_user_query reads from session_mode,
    # not from any global — so B's next query would route to local even while A is cloud.
    # The ws_handler wiring (session_mode variable) is what enforces this; we've
    # verified the handler API surface does not leak into a shared module variable.


@pytest.mark.asyncio
async def test_handle_set_project_path_returns_session_state_without_mutating_env(tmp_path, monkeypatch):
    project_dir = tmp_path / "project-a"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("print('a')\n", encoding="utf-8")

    original_env = "C:/sentinel/original"
    monkeypatch.setenv("PROJECT_PATH", original_env)

    events = []

    async def send_event(payload):
        events.append(payload)

    result = await jarvis_main._handle_set_project_path(
        {"path": str(project_dir)}, send_event,
    )

    assert result is not None
    new_path, codebase_map = result
    assert Path(new_path) == project_dir.resolve()
    assert "app.py" in codebase_map
    assert any(e.get("event") == "project_path_ack" for e in events)
    assert jarvis_main.os.environ["PROJECT_PATH"] == original_env


class _FakeWebSocket:
    """Minimal ws double: async-iterable over an inbound queue, captures sent bytes."""

    def __init__(self):
        import asyncio as _a
        self._in: _a.Queue = _a.Queue()
        self.sent: list[str] = []
        self._closed = False

    async def send(self, message):
        self.sent.append(message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self._in.get()
        if msg is None:  # sentinel → close the iterator
            raise StopAsyncIteration
        return msg

    async def inject(self, message: str):
        await self._in.put(message)

    async def close_iter(self):
        await self._in.put(None)


@pytest.mark.asyncio
async def test_consent_approve_resolves_during_query(monkeypatch, tmp_path):
    """P0 regression: while a user_query is blocked awaiting consent, the
    receive loop must still deliver the consent_response that unblocks it.

    Prior bug: ws_handler awaited _handle_user_query inline, so its own
    receive loop couldn't read the consent_response — every gated tool
    auto-denied at timeout even when the user approved."""
    import asyncio
    import json as _json

    from backend.ai import consent as consent_mod

    observed = {}

    async def _fake_claude_run(**kwargs):
        mgr = consent_mod.current()
        assert mgr is not None, "ConsentManager not inherited by spawned task"
        observed["approved"] = await mgr.request("test.gate", {"reason": "demo"})
        return f"approved={observed['approved']}"

    monkeypatch.setattr(jarvis_main, "claude_run", _fake_claude_run)
    _evt = asyncio.Event()
    _evt.set()
    monkeypatch.setattr(jarvis_main, "_codebase_ready", _evt)
    monkeypatch.setattr(jarvis_main, "_codebase_loaded", True)

    ws = _FakeWebSocket()
    handler_task = asyncio.create_task(jarvis_main.ws_handler(ws))

    await ws.inject(_json.dumps({"event": "user_query", "query": "do it"}))

    request_id = None
    for _ in range(200):
        await asyncio.sleep(0.01)
        for raw in ws.sent:
            ev = _json.loads(raw)
            if ev.get("event") == "consent_request":
                request_id = ev["request_id"]
                break
        if request_id:
            break
    assert request_id, "consent_request was never emitted — receive loop likely blocked"

    await ws.inject(_json.dumps({
        "event": "consent_response", "request_id": request_id, "approved": True,
    }))

    for _ in range(200):
        await asyncio.sleep(0.01)
        if "approved" in observed:
            break

    await ws.close_iter()
    await asyncio.wait_for(handler_task, timeout=2.0)

    # Future must have resolved True well under the 30s consent timeout.
    assert observed.get("approved") is True


@pytest.mark.asyncio
async def test_consent_deny_resolves_during_query(monkeypatch):
    """Denial path: consent_response approved:false flows through the receive
    loop to the spawned task's Future without timing out."""
    import asyncio
    import json as _json

    from backend.ai import consent as consent_mod

    observed = {}

    async def _fake_claude_run(**kwargs):
        mgr = consent_mod.current()
        observed["approved"] = await mgr.request("test.gate", {"reason": "demo"})
        return f"approved={observed['approved']}"

    monkeypatch.setattr(jarvis_main, "claude_run", _fake_claude_run)
    _evt = asyncio.Event()
    _evt.set()
    monkeypatch.setattr(jarvis_main, "_codebase_ready", _evt)
    monkeypatch.setattr(jarvis_main, "_codebase_loaded", True)

    ws = _FakeWebSocket()
    handler_task = asyncio.create_task(jarvis_main.ws_handler(ws))

    await ws.inject(_json.dumps({"event": "user_query", "query": "nope"}))

    request_id = None
    for _ in range(200):
        await asyncio.sleep(0.01)
        for raw in ws.sent:
            ev = _json.loads(raw)
            if ev.get("event") == "consent_request":
                request_id = ev["request_id"]
                break
        if request_id:
            break
    assert request_id

    await ws.inject(_json.dumps({
        "event": "consent_response", "request_id": request_id, "approved": False,
    }))

    for _ in range(200):
        await asyncio.sleep(0.01)
        if "approved" in observed:
            break

    await ws.close_iter()
    await asyncio.wait_for(handler_task, timeout=2.0)
    assert observed.get("approved") is False


@pytest.mark.asyncio
async def test_handle_user_query_threads_session_project_path(monkeypatch, tmp_path):
    captured = {}

    async def fake_claude_run(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(jarvis_main, "claude_run", fake_claude_run)
    monkeypatch.setattr(jarvis_main, "_codebase_ready", None)

    events = []

    async def send_event(payload):
        events.append(payload)

    project_dir = tmp_path / "project-b"
    project_dir.mkdir()

    history, codebase_map = await jarvis_main._handle_user_query(
        {"query": "Inspect this project"},
        send_event,
        [],
        "local",
        str(project_dir),
        "Project files (1 total):\n  app.py",
    )

    assert captured["project_path"] == str(project_dir)
    assert captured["codebase_map"].startswith("Project files")
    assert history == [
        {"role": "user", "content": "Inspect this project"},
        {"role": "assistant", "content": "ok"},
    ]
    assert codebase_map.startswith("Project files")
    assert any(e.get("event") == "status_update" for e in events)
