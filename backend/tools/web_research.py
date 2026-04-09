"""
web_research tool — scrapes the web using Playwright (async).

Parameters (from prompts/tool_schema.md):
  query: str       — search query (NOT a URL — tool builds the URL internally)
  max_results: int — number of results to return (default 5)

Playwright must be installed: pip install playwright && playwright install chromium
"""

import logging

logger = logging.getLogger("jarvis.web_research")

MAX_CONTENT_CHARS = 5000


async def run(query: str, max_results: int = 5) -> dict:
    """
    Searches Google for `query` and returns scraped page text.
    Returns {"query": str, "content": str, "url": str} or {"error": str}.
    """
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={max_results}"

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_extra_http_headers(
                    {"User-Agent": "Mozilla/5.0 (compatible; JARVIS/1.0)"}
                )
                await page.goto(url, timeout=15000)
                await page.wait_for_load_state("domcontentloaded")
                content = await page.inner_text("body")
                content = _clean(content)
                return {
                    "query": query,
                    "content": content[:MAX_CONTENT_CHARS],
                    "url": url,
                    "truncated": len(content) > MAX_CONTENT_CHARS,
                }
            finally:
                await browser.close()

    except ImportError:
        return {"error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}
    except Exception as e:
        logger.error(f"web_research error for '{query}': {e}")
        return {"error": str(e), "query": query}


def _clean(text: str) -> str:
    """Remove excessive whitespace from scraped text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
