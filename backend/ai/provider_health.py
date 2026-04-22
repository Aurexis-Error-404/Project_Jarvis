"""Per-provider success/failure/latency tracker.

Design rules — see JARVIS_IMPLEMENTATION_PLAN.md §8:
- Mutations guarded by an `asyncio.Lock` — the stats dict is shared across
  concurrent WebSocket handlers; unguarded increments race under load
  (audit issue HIGH-1 pattern).
- Rolling window of the last N calls (default 20). Older data ages out.
- A provider with success rate below `UNHEALTHY_THRESHOLD` (60%) is
  "unhealthy" for `QUARANTINE_SECONDS` (300 s). `sort_chain` pushes
  unhealthy providers to the back without removing them — fallback still
  works when everything is unhealthy.

Public surface:
  * `record_success(name, elapsed_ms)` / `record_failure(name, elapsed_ms)`
  * `is_healthy(name) -> bool`
  * `sort_chain(chain) -> list[str]` — stable reorder
  * `snapshot() -> dict` — for the `/health` endpoint
"""

from __future__ import annotations

import asyncio
import collections
import os
import time
from contextlib import asynccontextmanager
from typing import Final

WINDOW_SIZE: Final[int] = 20
UNHEALTHY_THRESHOLD: Final[float] = 0.60
QUARANTINE_SECONDS: Final[float] = 300.0

# Per-provider concurrent-request ceiling. Used by the orchestrator's
# fan-out path so three parallel sub-agents never all slam Gemini's 15 RPM
# free tier at once (§4.2 / Phase 2C rate-limit plan). Override via env
# for a stricter/looser ceiling without a code change.
_CONCURRENCY_DEFAULTS: dict[str, int] = {
    "gemini": int(os.environ.get("GEMINI_MAX_CONCURRENT", "2")),
    "groq":   int(os.environ.get("GROQ_MAX_CONCURRENT",   "6")),
    "ollama": int(os.environ.get("OLLAMA_MAX_CONCURRENT", "3")),
}


class _ProviderStats:
    __slots__ = ("results", "latencies_ms", "last_quarantine_at")

    def __init__(self):
        self.results: collections.deque[bool] = collections.deque(maxlen=WINDOW_SIZE)
        self.latencies_ms: collections.deque[float] = collections.deque(maxlen=WINDOW_SIZE)
        self.last_quarantine_at: float = 0.0

    def success_rate(self) -> float:
        if not self.results:
            return 1.0
        return sum(self.results) / len(self.results)

    def avg_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)


class ProviderHealth:
    """Thread-safe rolling health tracker for LLM providers."""

    def __init__(self):
        self._stats: dict[str, _ProviderStats] = {}
        self._lock = asyncio.Lock()
        # Lazily created so a Semaphore isn't bound to an event loop at
        # import time (tests create/destroy loops).
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        # Defensive default for unknown providers — avoids unbounded
        # concurrency on a typo'd provider name.
        self._default_concurrency = 4

    def _semaphore(self, name: str) -> asyncio.Semaphore:
        sem = self._semaphores.get(name)
        if sem is None:
            limit = _CONCURRENCY_DEFAULTS.get(name, self._default_concurrency)
            sem = asyncio.Semaphore(limit)
            self._semaphores[name] = sem
        return sem

    @asynccontextmanager
    async def slot(self, name: str):
        """Bound concurrent in-flight calls per provider.

        Usage:
            async with HEALTH.slot("gemini"):
                await _call_provider(...)

        The ceiling comes from `_CONCURRENCY_DEFAULTS` (env-overridable).
        Tracks waiters implicitly — callers back up in FIFO order behind
        the semaphore. Pair this with the health quarantine above to give
        fan-out + retry headroom without breaching provider RPM limits.
        """
        sem = self._semaphore(name)
        await sem.acquire()
        try:
            yield
        finally:
            sem.release()

    def _stats_for(self, name: str) -> _ProviderStats:
        s = self._stats.get(name)
        if s is None:
            s = _ProviderStats()
            self._stats[name] = s
        return s

    async def record_success(self, name: str, elapsed_ms: float) -> None:
        async with self._lock:
            s = self._stats_for(name)
            s.results.append(True)
            s.latencies_ms.append(float(elapsed_ms))

    async def record_failure(self, name: str, elapsed_ms: float = 0.0) -> None:
        async with self._lock:
            s = self._stats_for(name)
            s.results.append(False)
            if elapsed_ms:
                s.latencies_ms.append(float(elapsed_ms))
            if s.success_rate() < UNHEALTHY_THRESHOLD and len(s.results) >= 5:
                s.last_quarantine_at = time.monotonic()

    def is_healthy(self, name: str) -> bool:
        """Non-locking read — the stats dict mutation is atomic at the dict
        level; approximate reads are acceptable for routing decisions."""
        s = self._stats.get(name)
        if s is None:
            return True
        if s.last_quarantine_at and (
            time.monotonic() - s.last_quarantine_at < QUARANTINE_SECONDS
        ):
            return False
        return True

    def sort_chain(self, chain: list[str]) -> list[str]:
        """Stable: healthy providers keep their relative order, unhealthy
        ones get pushed to the back. Never drops a provider — the caller's
        fallback logic already handles "all chains exhausted"."""
        healthy = [p for p in chain if self.is_healthy(p)]
        unhealthy = [p for p in chain if not self.is_healthy(p)]
        return healthy + unhealthy

    def snapshot(self) -> dict:
        """Point-in-time view for observability (logs, /health)."""
        out: dict[str, dict] = {}
        for name, s in self._stats.items():
            out[name] = {
                "success_rate": round(s.success_rate(), 3),
                "avg_latency_ms": round(s.avg_latency_ms(), 1),
                "samples": len(s.results),
                "quarantined": not self.is_healthy(name),
            }
        return out


# Module-level singleton. One process → one health tracker.
HEALTH = ProviderHealth()
