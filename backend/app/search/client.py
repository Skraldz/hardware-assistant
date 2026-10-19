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


class SearchClient(Protocol):
    def search(self, query: str) -> list[SearchCandidate]: ...


class SearxngClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str) -> list[SearchCandidate]:
        response = httpx.get(
            f"{self._base_url}/search",
            params={"q": query, "format": "json"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])[:MAX_CANDIDATES]
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
