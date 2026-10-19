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
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["response"]
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Kunne ikke nå Ollama: {exc}") from exc

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
