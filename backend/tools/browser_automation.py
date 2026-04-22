"""Tier 2 browser automation — Playwright wrapper (§7.1 / §7.6).

Off by default: `BROWSER_AUTOMATION_ENABLED=1` to opt in. Every call
already has consent from the dispatcher's `_pre_tool_check` hook — this
module does not re-prompt.

Guardrails:
- **Per-domain allowlist** from `BROWSER_ALLOW_DOMAINS` (comma-separated).
  Requests to any other domain return an error.
- Screenshots go to `<workspace>/.claude/temp/browser/`, NOT `reports/`.
- Playwright import is optional — absent → fail-closed error dict.
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urlparse

logger = logging.getLogger("jarvis.browser_automation")

BROWSER_AUTOMATION_ENABLED: bool = os.environ.get("BROWSER_AUTOMATION_ENABLED", "0").lower() in (
    "1", "true", "yes",
)
_ALLOW_DOMAINS_RAW = os.environ.get("BROWSER_ALLOW_DOMAINS", "")


def _parse_allowlist(raw: str) -> list[str]:
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def is_domain_allowed(url: str, allowlist: list[str] | None = None) -> bool:
    """Return True iff `url`'s host matches an allowlisted domain (suffix match)."""
    if allowlist is None:
        allowlist = _parse_allowlist(_ALLOW_DOMAINS_RAW)
    if not allowlist:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    # Suffix match: "docs.python.org" is allowed by "python.org".
    for allowed in allowlist:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def _screenshot_dir() -> str:
    from backend.context.workspace import current_path
    out = os.path.join(current_path(), ".claude", "temp", "browser")
    os.makedirs(out, exist_ok=True)
    return out


async def run(action: str, url: str = "", **kwargs) -> dict:
    """Async entry point. Supported actions: navigate, dom_text, screenshot."""
    if not BROWSER_AUTOMATION_ENABLED:
        return {"error": "browser automation disabled (set BROWSER_AUTOMATION_ENABLED=1 to enable)"}
    if action not in {"navigate", "dom_text", "screenshot"}:
        return {"error": f"unsupported action: {action!r}"}
    if not url:
        return {"error": "url is required"}
    if not is_domain_allowed(url):
        return {"error": f"domain not on allowlist: {url}"}

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as e:  # noqa: BLE001
        return {"error": f"playwright unavailable: {e}"}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=int(kwargs.get("timeout_ms", 15000)))
                if action == "navigate":
                    return {"ok": True, "url": page.url, "title": await page.title()}
                if action == "dom_text":
                    sel = kwargs.get("selector", "body")
                    text = await page.inner_text(sel)
                    # Cap to avoid flooding the agent context.
                    cap = int(kwargs.get("max_chars", 8000))
                    return {"ok": True, "url": page.url, "text": text[:cap],
                            "truncated": len(text) > cap}
                if action == "screenshot":
                    path = os.path.join(_screenshot_dir(),
                                        f"shot_{int(time.time() * 1000)}.png")
                    await page.screenshot(path=path, full_page=bool(kwargs.get("full_page", False)))
                    return {"ok": True, "path": path, "url": page.url}
            finally:
                await browser.close()
    except Exception as e:
        logger.exception("browser_automation failed")
        return {"error": f"{action} failed: {e}"}

    return {"error": "unreachable"}


# Exposed for tests.
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9.-]+$")
