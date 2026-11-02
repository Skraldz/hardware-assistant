"""Fetches and cleans a single web page's visible text for the extraction
LLM (routers/components.py's /api/components/extract).

A SearXNG result's `snippet` (search/client.py) is a short preview the
search engine generated -- often a meta description -- not the page itself.
A spec table or bullet list commonly sits further down the actual page than
any such snippet ever reaches, so the extraction LLM was missing fields
(e.g. PCIe power connectors) that genuinely are on the page, just not in the
short preview it was given. This fetches the chosen candidate's real page
and reduces it to plain visible text, giving the LLM far more of the actual
content to work with.

`PageFetcher` is a Protocol (same pattern as search/client.py's
SearchClient) so tests never make a real HTTP request (SPEC.md §9.1).
Best-effort only: any failure (network, timeout, non-HTML, oversized
response) returns None rather than raising -- a page that can't be fetched
just falls back to the snippet-only behavior that already existed.
"""

from typing import Protocol

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

# Tags whose content is never part of a page's visible, readable text.
_SKIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "form"]


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str | None: ...


class HttpPageFetcher:
    def fetch(self, url: str) -> str | None:
        settings = get_settings()
        if not settings.fetch_full_page:
            return None
        try:
            response = httpx.get(
                url,
                timeout=settings.page_fetch_timeout_s,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; HardwareAssistantBot/1.0)"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        if "html" not in response.headers.get("content-type", ""):
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(_SKIP_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[: settings.page_fetch_max_chars] or None


def get_page_fetcher() -> PageFetcher:
    """FastAPI dependency. Overridden with a fake in tests."""
    return HttpPageFetcher()
