"""Per-action consent manager for gated tools (§7.2).

Flow:
  1. Tool dispatcher (or agent `_pre_tool_check`) calls `request(...)`.
  2. Manager creates a request_id, stores an `asyncio.Future`, and fires
     a `consent_request` WebSocket event via the send_event callback
     threaded in by the ws handler.
  3. Frontend renders the `ConsentDialog`, user approves or denies,
     sends back `consent_response` with the same request_id.
  4. The ws handler calls `resolve(request_id, approved)`, unblocking
     the awaiting tool dispatch.
  5. Every decision — including timeout auto-denies — is appended to
     the workspace audit log (`.claude/audit.log`).

Design rules:
- **Fail-closed.** No send_event registered → auto-deny. Timeout → deny.
- **Per-session.** Each WebSocket connection gets its own manager so a
  consent prompt on one window can't be answered from another.
- **Blocking await** on the dispatcher side; the tool never runs before
  the dialog resolves.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Final

from backend.ai.audit import append_audit

logger = logging.getLogger("jarvis.consent")

CONSENT_TIMEOUT_SECONDS: Final[float] = 30.0

SendEvent = Callable[[dict], Awaitable[None]]


@dataclass
class _PendingRequest:
    action: str
    payload: dict
    future: asyncio.Future = field(repr=False)


class ConsentManager:
    """Per-session consent coordinator. One instance per WebSocket."""

    def __init__(self, send_event: SendEvent | None = None,
                 project_path: str | None = None):
        self._send_event = send_event
        self._project_path = project_path
        self._pending: dict[str, _PendingRequest] = {}
        self._lock = asyncio.Lock()

    def bind(self, send_event: SendEvent, project_path: str | None) -> None:
        """Attach or update the session's send_event + workspace root."""
        self._send_event = send_event
        self._project_path = project_path

    async def request(self, action: str, payload: dict) -> bool:
        """Ask the user to approve `action`. Returns True iff approved."""
        if self._send_event is None:
            logger.warning(f"consent denied (no UI bound) action={action}")
            append_audit(self._project_path, action, payload,
                         decision="denied_no_ui")
            return False

        request_id = secrets.token_urlsafe(12)
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        async with self._lock:
            self._pending[request_id] = _PendingRequest(
                action=action, payload=payload, future=fut,
            )

        try:
            await self._send_event({
                "event": "consent_request",
                "request_id": request_id,
                "action": action,
                "payload": payload,
                "timeout_s": CONSENT_TIMEOUT_SECONDS,
            })
        except Exception as e:
            logger.warning(f"failed to send consent_request: {e}")
            async with self._lock:
                self._pending.pop(request_id, None)
            append_audit(self._project_path, action, payload,
                         decision="denied_send_failed")
            return False

        try:
            approved = await asyncio.wait_for(fut, timeout=CONSENT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.info(f"consent timeout action={action} id={request_id}")
            approved = False
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

        decision = "approved" if approved else "denied"
        append_audit(self._project_path, action, payload, decision=decision)
        return approved

    async def resolve(self, request_id: str, approved: bool) -> bool:
        """Called by the ws handler when a `consent_response` arrives."""
        async with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            logger.warning(f"consent_response for unknown id={request_id}")
            return False
        if not pending.future.done():
            pending.future.set_result(bool(approved))
        return True


# ContextVar so downstream code (tool dispatcher) can pull the active
# session's ConsentManager without threading it through many layers —
# the same pattern as `backend.context.workspace`.
_ACTIVE: ContextVar[ConsentManager | None] = ContextVar(
    "jarvis_consent_manager", default=None,
)


def set_active(manager: ConsentManager):
    """Bind `manager` as the active ConsentManager for the current context."""
    return _ACTIVE.set(manager)


def reset_active(token) -> None:
    _ACTIVE.reset(token)


def current() -> ConsentManager | None:
    """Return the ConsentManager bound to the current context, or None."""
    return _ACTIVE.get()
