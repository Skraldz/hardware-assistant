"""Unit tests for HttpPageFetcher (mocked httpx -- never a real web page,
per SPEC.md §9.1). The API-level merge into the extraction prompt is
covered separately in test_api_llm_endpoints.py via FakePageFetcher."""

from unittest.mock import MagicMock, patch

import httpx

from app.config import Settings
from app.search.page_fetch import HttpPageFetcher


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_strips_script_style_and_nav_returning_only_visible_text(mock_get, mock_settings):
    mock_settings.return_value = Settings()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.headers = {"content-type": "text/html; charset=utf-8"}
    response.text = (
        "<html><head><style>.x{color:red}</style></head><body>"
        "<nav>Home | Products</nav>"
        "<script>trackPageView();</script>"
        "<h1>RTX 2060 SUPER</h1>"
        "<p>PCIe power connectors: 1x 8-pin</p>"
        "<footer>Copyright 2024</footer>"
        "</body></html>"
    )
    mock_get.return_value = response

    text = HttpPageFetcher().fetch("https://example.com/rtx-2060-super")

    assert text is not None
    assert "PCIe power connectors: 1x 8-pin" in text
    assert "RTX 2060 SUPER" in text
    assert "trackPageView" not in text
    assert "color:red" not in text
    assert "Home | Products" not in text
    assert "Copyright 2024" not in text


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_truncates_to_the_configured_max_chars(mock_get, mock_settings):
    mock_settings.return_value = Settings(page_fetch_max_chars=20)
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.headers = {"content-type": "text/html"}
    response.text = "<p>" + ("x" * 1000) + "</p>"
    mock_get.return_value = response

    text = HttpPageFetcher().fetch("https://example.com")

    assert len(text) == 20


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_returns_none_on_a_connection_error(mock_get, mock_settings):
    mock_settings.return_value = Settings()
    mock_get.side_effect = httpx.ConnectError("connection refused")

    assert HttpPageFetcher().fetch("https://example.com") is None


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_returns_none_on_an_http_error_status(mock_get, mock_settings):
    mock_settings.return_value = Settings()
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "not found", request=MagicMock(), response=MagicMock(status_code=404)
    )
    mock_get.return_value = response

    assert HttpPageFetcher().fetch("https://example.com") is None


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_returns_none_for_a_non_html_response(mock_get, mock_settings):
    mock_settings.return_value = Settings()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.headers = {"content-type": "application/pdf"}
    mock_get.return_value = response

    assert HttpPageFetcher().fetch("https://example.com/datasheet.pdf") is None


@patch("app.search.page_fetch.get_settings")
@patch("app.search.page_fetch.httpx.get")
def test_fetch_returns_none_when_disabled(mock_get, mock_settings):
    mock_settings.return_value = Settings(fetch_full_page=False)

    assert HttpPageFetcher().fetch("https://example.com") is None
    mock_get.assert_not_called()
