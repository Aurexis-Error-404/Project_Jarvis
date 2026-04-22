"""Concurrency + ordering tests for backend/ai/provider_health.py.

§8.4 calls out the race-condition risk on shared stats. These tests
exercise the asyncio.Lock path with gather() and verify the chain sort
is stable.
"""

import asyncio

import pytest

from backend.ai.provider_health import (
    QUARANTINE_SECONDS,
    UNHEALTHY_THRESHOLD,
    ProviderHealth,
)


@pytest.mark.asyncio
async def test_record_success_increments_under_gather():
    h = ProviderHealth()

    async def one():
        await h.record_success("groq", 100.0)

    await asyncio.gather(*(one() for _ in range(15)))
    snap = h.snapshot()["groq"]
    assert snap["samples"] == 15
    assert snap["success_rate"] == 1.0
    assert snap["quarantined"] is False


@pytest.mark.asyncio
async def test_mixed_success_failure_drives_quarantine():
    h = ProviderHealth()

    # 8 failures vs 2 successes → 20% success rate → unhealthy.
    tasks = []
    for _ in range(8):
        tasks.append(h.record_failure("gemini", 50.0))
    for _ in range(2):
        tasks.append(h.record_success("gemini", 100.0))
    await asyncio.gather(*tasks)

    assert h.is_healthy("gemini") is False
    snap = h.snapshot()["gemini"]
    assert snap["success_rate"] < UNHEALTHY_THRESHOLD
    assert snap["quarantined"] is True


@pytest.mark.asyncio
async def test_healthy_provider_stays_first_in_chain():
    h = ProviderHealth()
    # gemini is fine, groq becomes unhealthy
    await asyncio.gather(*(h.record_success("gemini", 100.0) for _ in range(5)))
    for _ in range(6):
        await h.record_failure("groq", 10.0)
    for _ in range(2):
        await h.record_success("groq", 10.0)

    original = ["gemini", "groq"]
    sorted_chain = h.sort_chain(original)
    assert sorted_chain == ["gemini", "groq"]  # already in healthy-first order

    reversed_chain = ["groq", "gemini"]
    # Unhealthy groq should move behind healthy gemini.
    assert h.sort_chain(reversed_chain) == ["gemini", "groq"]


@pytest.mark.asyncio
async def test_unknown_provider_is_healthy_by_default():
    h = ProviderHealth()
    assert h.is_healthy("brand_new_provider") is True
    assert h.sort_chain(["brand_new_provider"]) == ["brand_new_provider"]


@pytest.mark.asyncio
async def test_snapshot_shape():
    h = ProviderHealth()
    await h.record_success("groq", 42.0)
    await h.record_failure("groq", 90.0)
    snap = h.snapshot()
    assert "groq" in snap
    assert set(snap["groq"].keys()) == {"success_rate", "avg_latency_ms", "samples", "quarantined"}
    assert snap["groq"]["samples"] == 2


@pytest.mark.asyncio
async def test_quarantine_expires_after_window(monkeypatch):
    """Lift the clock past QUARANTINE_SECONDS and the provider returns."""
    h = ProviderHealth()

    # Force quarantine.
    for _ in range(6):
        await h.record_failure("gemini")
    assert h.is_healthy("gemini") is False

    import backend.ai.provider_health as ph
    # Jump time forward past the quarantine window.
    frozen = ph.time.monotonic() + QUARANTINE_SECONDS + 10
    monkeypatch.setattr(ph.time, "monotonic", lambda: frozen)
    assert h.is_healthy("gemini") is True
