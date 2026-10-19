"""Unit tests for OllamaClient's own HTTP-error wrapping (mocked httpx —
never a real Ollama, per SPEC.md §9.1). The retry/fallback behavior this
enables is covered separately in test_llm_parsing.py via FakeLLMClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from app.llm.client import LLMUnavailableError, OllamaClient


class DummySchema(BaseModel):
    value: str = "x"


@patch("app.llm.client.httpx.post")
def test_generate_structured_wraps_connection_error(mock_post):
    mock_post.side_effect = httpx.ConnectError("connection refused")
    client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b-instruct", timeout=5.0)

    with pytest.raises(LLMUnavailableError, match="Kunne ikke nå Ollama"):
        client.generate_structured(system="s", prompt="p", schema=DummySchema)


@patch("app.llm.client.httpx.post")
def test_generate_structured_wraps_http_status_error(mock_post):
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=MagicMock(status_code=500)
    )
    mock_post.return_value = response
    client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b-instruct", timeout=5.0)

    with pytest.raises(LLMUnavailableError):
        client.generate_structured(system="s", prompt="p", schema=DummySchema)


@patch("app.llm.client.httpx.post")
def test_generate_structured_returns_raw_response_text(mock_post):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": '{"value": "ok"}'}
    mock_post.return_value = response
    client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b-instruct", timeout=5.0)

    raw = client.generate_structured(system="s", prompt="p", schema=DummySchema)

    assert raw == '{"value": "ok"}'


@patch("app.llm.client.httpx.get")
def test_ping_returns_false_on_connection_error(mock_get):
    mock_get.side_effect = httpx.ConnectError("connection refused")
    client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b-instruct", timeout=5.0)

    assert client.ping() is False


@patch("app.llm.client.httpx.get")
def test_ping_returns_true_on_200(mock_get):
    mock_get.return_value = MagicMock(status_code=200)
    client = OllamaClient(base_url="http://ollama:11434", model="qwen2.5:7b-instruct", timeout=5.0)

    assert client.ping() is True
