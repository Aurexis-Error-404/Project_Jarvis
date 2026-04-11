"""
web_research tool — searches the web using httpx (fast, no browser overhead).

Parameters (from prompts/tool_schema.md):
  query: str       — search query
  max_results: int — number of results to return (default 5)

Uses DuckDuckGo HTML search (no API key needed, no rate limits like Google).
Falls back to direct URL fetch if DDG fails.
"""

import logging
import re
from urllib.parse import quote, urljoin

import httpx

logger = logging.getLogger("jarvis.web_research")

MAX_CONTENT_CHARS = 6000
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML — strip tags, scripts, styles."""
    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<noscript[^>]*>[\s\S]*?</noscript>", "", html, flags=re.IGNORECASE)
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_ddg_results(html: str) -> list[dict]:
    """Extract search result titles, URLs, and snippets from DuckDuckGo HTML."""
    results = []
    # DuckDuckGo result links have class="result__a"
    # Pattern: find result blocks
    result_blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for url, title, snippet in result_blocks:
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        if url and clean_title:
            results.append({"url": url, "title": clean_title, "snippet": clean_snippet})

    # Fallback: try alternate DDG layout pattern
    if not results:
        links = re.findall(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL | re.IGNORECASE,
        )
        seen_urls = set()
        for url, title in links:
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            if (
                url not in seen_urls
                and clean_title
                and len(clean_title) > 10
                and "duckduckgo" not in url.lower()
                and not url.endswith((".css", ".js", ".png", ".jpg"))
            ):
                seen_urls.add(url)
                results.append({"url": url, "title": clean_title, "snippet": ""})
                if len(results) >= 8:
                    break

    return results


async def _fetch_page_content(client: httpx.AsyncClient, url: str) -> str:
    """Fetch and extract text content from a URL."""
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        text = _extract_text_from_html(r.text)
        # Cap per-page content
        return text[:3000] if text else ""
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return ""


async def run(query: str, max_results: int = 5) -> dict:
    """
    Searches DuckDuckGo for `query`, fetches top result pages, and returns
    structured content for the AI model.

    Returns {"query", "results": [...], "content"} or {"error"}.
    """
    search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
            # Step 1: Search DuckDuckGo
            r = await client.get(search_url)
            r.raise_for_status()

            results = _extract_ddg_results(r.text)[:max_results]

            if not results:
                # Fallback: extract text from the search page itself
                page_text = _extract_text_from_html(r.text)
                if page_text and len(page_text) > 100:
                    return {
                        "query": query,
                        "results": [],
                        "content": page_text[:MAX_CONTENT_CHARS],
                        "source": "ddg_page_text",
                    }
                return {"error": f"No results found for: {query}", "query": query}

            # Step 2: Fetch top result pages for richer content
            contents = []
            for result in results[:3]:  # Fetch top 3 for depth
                page_text = await _fetch_page_content(client, result["url"])
                if page_text:
                    contents.append(f"### {result['title']}\nSource: {result['url']}\n{page_text}")

            # Combine search snippets + page content
            snippet_text = "\n\n".join(
                f"**{r['title']}** ({r['url']})\n{r['snippet']}"
                for r in results
            )

            full_content = snippet_text
            if contents:
                full_content += "\n\n---\n\n" + "\n\n".join(contents)

            return {
                "query": query,
                "results": results,
                "content": full_content[:MAX_CONTENT_CHARS],
                "result_count": len(results),
                "pages_fetched": len(contents),
            }

    except httpx.ConnectError:
        return {"error": "Network error — cannot reach search engine", "query": query}
    except Exception as e:
        logger.error(f"web_research error for '{query}': {e}")
        return {"error": str(e), "query": query}
