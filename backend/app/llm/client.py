"""Thin client around Ollama's structured-output API.

`LLMClient` is a Protocol so tests can swap in a fake without touching
Ollama (SPEC.md §9.1: no test may require Ollama). Both the real client and
fakes return the model's raw text; validating that text against a Pydantic
schema is `llm/parsing.py`'s job, not the client's.
"""

from functools import lru_cache
from typing import Protocol

import httpx
from pydantic import BaseModel

from app.config import get_settings


class LLMUnavailableError(RuntimeError):
    """Ollama couldn't be reached or returned an error. Treated the same as
    an invalid response by llm/parsing.py's retry/fallback — a down Ollama
    must never crash a request (SPEC.md §2)."""


class LLMClient(Protocol):
    def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]) -> str: ...

    def ping(self) -> bool: ...


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]) -> str:
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "system": system,
                    "prompt": prompt,
                    "format": schema.model_json_schema(),
                    "stream": False,
                    # Deterministic sampling: without this, Ollama's default
                    # temperature means identical prompts (e.g. re-ranking
                    # the same builds on a follow-up question that didn't
                    # change the requirements) can still produce different
                    # output from one call to the next -- undermining both
                    # schema-field-filling consistency and the frontend's
                    # "builds unchanged" comparison (RecommendView.jsx).
                    "options": {"temperature": 0},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Could not reach Ollama: {exc}") from exc
        try:
            # A 200 whose body isn't the JSON shape we expect (a truncated
            # response, a proxy's error page, an Ollama API change) must be
            # treated as "LLM unavailable" like any transport failure --
            # otherwise it escapes call_llm_with_retry's error handling as a
            # raw KeyError/JSONDecodeError and becomes a 500, breaking the
            # invariant that a misbehaving Ollama never crashes a request.
            return response.json()["response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMUnavailableError(f"Unexpected response from Ollama: {exc}") from exc

    def ping(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False


@lru_cache
def get_ollama_client() -> OllamaClient:
    settings = get_settings()
    return OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_request_timeout_s,
    )


def get_llm_client() -> LLMClient:
    """FastAPI dependency. Overridden with a fake in tests."""
    return get_ollama_client()
