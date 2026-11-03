"""Thin client around SearXNG's JSON search API, used by
/api/components/search to find candidate pages for a hardware name typed by
the user. `SearchClient` is a Protocol so tests never hit a real SearXNG
instance (SPEC.md §9.1).
"""

from typing import Protocol

import httpx

from app.config import get_settings
from app.schemas.search import SearchCandidate

MAX_CANDIDATES = 5

# Marketplace/retailer domains to steer results away from: their listings are
# written to sell, not to document specs, which was giving the extraction LLM
# marketing copy instead of the actual numbers it needs (see docs/ai-log.md).
# `-site:`/`site:` is standard search-operator syntax most of SearXNG's
# underlying engines (Google, Bing, DuckDuckGo, ...) honor directly in the
# query text -- not verified against a real SearXNG instance, see Known risks.
_EXCLUDED_DOMAINS = ["amazon.com", "ebay.com", "dba.dk", "newegg.com"]


def _build_query(name: str) -> str:
    """Biases the search toward pages that actually document specifications
    (manufacturer product pages, review/database sites like TechPowerUp or
    PCPartPicker) instead of shopping listings."""
    exclusions = " ".join(f"-site:{domain}" for domain in _EXCLUDED_DOMAINS)
    return f"{name} specifications {exclusions}"


class SearchUnavailableError(RuntimeError):
    """SearXNG couldn't be reached or returned an error."""


class SearchClient(Protocol):
    """Finds candidate web pages for a hardware name.

    A Protocol so tests never hit a real SearXNG instance (SPEC.md 9.1).
    """

    def search(self, query: str) -> list[SearchCandidate]:
        """Find candidate pages documenting a component.

        Args:
            query: The component name the user typed.

        Returns:
            list[SearchCandidate]: Pages for the user to choose from.
        """
        ...


class SearxngClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        """Configure the SearXNG endpoint.

        Args:
            base_url: SearXNG base URL.
            timeout: Per-request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str) -> list[SearchCandidate]:
        """Search SearXNG for pages documenting a component.

        Args:
            query: The component name the user typed.

        Returns:
            list[SearchCandidate]: Up to MAX_CANDIDATES results, biased toward
                spec pages and away from retail listings.

        Raises:
            SearchUnavailableError: SearXNG could not be reached, or answered
                with something other than JSON -- which is what it does when its
                `json` output format is left disabled.
        """
        try:
            response = httpx.get(
                f"{self._base_url}/search",
                params={"q": _build_query(query), "format": "json"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchUnavailableError(f"Could not reach SearXNG: {exc}") from exc
        try:
            # SearXNG ships with its `json` output format *disabled* by
            # default, and then answers /search?format=json with HTTP 200
            # and an HTML error page. Without this, response.json() raises a
            # bare JSONDecodeError that escapes both this method's error
            # contract and the router's `except SearchUnavailableError`, so
            # the user gets an opaque 500 instead of the intended 503.
            results = response.json().get("results", [])[:MAX_CANDIDATES]
        except (ValueError, AttributeError) as exc:
            raise SearchUnavailableError(
                f"SearXNG did not return JSON results (is the 'json' output format enabled?): {exc}"
            ) from exc
        return [
            SearchCandidate(
                title=result.get("title", ""),
                url=result.get("url", ""),
                snippet=result.get("content", ""),
            )
            for result in results
        ]


def get_search_client() -> SearchClient:
    """FastAPI dependency. Overridden with a fake in tests."""
    settings = get_settings()
    return SearxngClient(base_url=settings.searxng_base_url)
