"""Tests for §7.1 browser automation allowlist + fail-closed behaviour."""

from __future__ import annotations

import asyncio

import pytest

from backend.tools import browser_automation as ba


# ─── Allowlist ────────────────────────────────────────────────────────────

def test_exact_host_allowed():
    assert ba.is_domain_allowed("https://github.com/foo", ["github.com"]) is True


def test_subdomain_allowed_via_suffix():
    assert ba.is_domain_allowed("https://docs.python.org/3/", ["python.org"]) is True


def test_non_matching_host_blocked():
    assert ba.is_domain_allowed("https://evil.com/phish", ["github.com"]) is False


def test_lookalike_suffix_blocked():
    # "notgithub.com" must NOT match "github.com".
    assert ba.is_domain_allowed("https://notgithub.com/x", ["github.com"]) is False


def test_empty_allowlist_blocks_everything():
    assert ba.is_domain_allowed("https://github.com/foo", []) is False


def test_malformed_url_blocked():
    assert ba.is_domain_allowed("not a url", ["github.com"]) is False


# ─── Disabled / missing deps ──────────────────────────────────────────────

def test_run_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ba, "BROWSER_AUTOMATION_ENABLED", False)
    result = asyncio.run(ba.run("navigate", url="https://github.com"))
    assert "error" in result
    assert "disabled" in result["error"]


def test_run_rejects_non_allowlisted_domain(monkeypatch):
    monkeypatch.setattr(ba, "BROWSER_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(ba, "_ALLOW_DOMAINS_RAW", "github.com")
    result = asyncio.run(ba.run("navigate", url="https://evil.example/"))
    assert "error" in result
    assert "allowlist" in result["error"]


def test_run_rejects_unsupported_action(monkeypatch):
    monkeypatch.setattr(ba, "BROWSER_AUTOMATION_ENABLED", True)
    result = asyncio.run(ba.run("evil_action", url="https://github.com"))
    assert "error" in result
    assert "unsupported" in result["error"]


def test_run_requires_url(monkeypatch):
    monkeypatch.setattr(ba, "BROWSER_AUTOMATION_ENABLED", True)
    result = asyncio.run(ba.run("navigate", url=""))
    assert "error" in result
