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
    """Fetches a web page and reduces it to readable text.

    A Protocol so tests never make a real HTTP request (SPEC.md 9.1).
    """

    def fetch(self, url: str) -> str | None:
        """Fetch and clean one page's visible text.

        Args:
            url: The page to fetch.

        Returns:
            str | None: The visible text, or None if it could not be had --
                callers fall back to the search snippet rather than failing.
        """
        ...


class HttpPageFetcher:
    """Fetches a page over HTTP and strips it to readable text.

    Exists because a search engine's snippet is a short preview, while the
    specification table usually sits further down the real page. Fetching
    the page gives the extraction model far more of the actual content.

    Note the URL comes from the request body and is not yet validated, so
    this can be pointed at internal addresses -- tracked as issue #9.
    """

    def fetch(self, url: str) -> str | None:
        """Fetch a page and reduce it to plain visible text.

        Best-effort: every failure returns None, falling back to the
        snippet-only extraction that already existed.

        Args:
            url: The page to fetch.

        Returns:
            str | None: Visible text truncated to page_fetch_max_chars, or None
                when fetching is disabled, the request fails, the response is
                not HTML, or the text is empty.
        """
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
