"""Unit tests for SearxngClient's own HTTP-error wrapping (mocked httpx —
never a real SearXNG, per SPEC.md §9.1). The API-level 503 behavior this
enables is covered separately in test_api_llm_endpoints.py via FakeSearchClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.search.client import SearchUnavailableError, SearxngClient


@patch("app.search.client.httpx.get")
def test_search_wraps_connection_error(mock_get):
    mock_get.side_effect = httpx.ConnectError("connection refused")
    client = SearxngClient(base_url="http://searxng:8080")

    with pytest.raises(SearchUnavailableError, match="Could not reach SearXNG"):
        client.search("rtx 2060 super")


@patch("app.search.client.httpx.get")
def test_search_wraps_http_status_error(mock_get):
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=MagicMock(status_code=500)
    )
    mock_get.return_value = response
    client = SearxngClient(base_url="http://searxng:8080")

    with pytest.raises(SearchUnavailableError):
        client.search("rtx 2060 super")


@patch("app.search.client.httpx.get")
def test_search_returns_candidates_on_success(mock_get):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [{"title": "RTX 2060 SUPER", "url": "https://example.com", "content": "8GB GDDR6"}]
    }
    mock_get.return_value = response
    client = SearxngClient(base_url="http://searxng:8080")

    candidates = client.search("rtx 2060 super")

    assert len(candidates) == 1
    assert candidates[0].title == "RTX 2060 SUPER"
