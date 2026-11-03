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
    """Talks to a language model that can be constrained to a schema.

    A Protocol so tests can swap in a fake without touching Ollama
    (SPEC.md 9.1). Implementations return the model's raw text; validating
    it against a schema is llm/parsing.py's job, not the client's.
    """

    def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]) -> str:
        """Ask the model for JSON matching a schema.

        Args:
            system: System prompt.
            prompt: User prompt.
            schema: Pydantic model constraining the output.

        Returns:
            str: The model's raw text, not yet validated.
        """
        ...

    def ping(self) -> bool:
        """Whether the model server is reachable.

        Returns:
            bool: True when the server answers.
        """
        ...


class OllamaClient:
    """Talks to a running Ollama instance.

    Sets two options deliberately on every call: temperature 0, so the same
    prompt gives the same answer and a follow-up question cannot silently
    reshuffle builds the user is already looking at; and an explicit
    `num_ctx`, because Ollama otherwise picks its own and truncates without
    error when a prompt overflows it -- which silently discarded the fetched
    page text that web lookup exists to provide.
    """

    def __init__(self, base_url: str, model: str, timeout: float, num_ctx: int) -> None:
        """Configure the Ollama endpoint.

        Args:
            base_url: Ollama's base URL.
            model: Model tag, e.g. "qwen2.5:7b-instruct".
            timeout: Per-request timeout in seconds.
            num_ctx: Context window. Set explicitly because Ollama otherwise
                picks its own and truncates silently on overflow.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._num_ctx = num_ctx

    def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]) -> str:
        """Ask Ollama for JSON constrained to a schema.

        The schema is passed in the `format` parameter, which restricts sampling
        to exactly that shape. Temperature is 0 so the same prompt gives the same
        answer.

        Args:
            system: System prompt.
            prompt: User prompt.
            schema: Pydantic model whose JSON schema constrains the output.

        Returns:
            str: The model's raw text. Validating it is llm/parsing.py's job.

        Raises:
            LLMUnavailableError: Ollama could not be reached, returned an error,
                or returned a 200 whose body is not the expected JSON shape --
                all treated alike so a misbehaving Ollama never becomes a 500.
        """
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
                    # num_ctx is set explicitly because Ollama otherwise applies
                    # its own default (2048 in older builds, 4096 in current
                    # ones) and does not fail on overflow -- it silently drops
                    # the oldest tokens. The /extract prompt carries up to
                    # page_fetch_max_chars of fetched page text, so an
                    # unconfigured context window quietly truncates away the
                    # very content the web lookup fetched, and the model looks
                    # like it "missed" fields it was never shown.
                    "options": {"temperature": 0, "num_ctx": self._num_ctx},
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
        """Whether Ollama answers.

        Returns:
            bool: True when /api/tags returns 200. Does not verify that the
                configured model is actually pulled.
        """
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False


@lru_cache
def get_ollama_client() -> OllamaClient:
    """Build the Ollama client from settings, cached per process."""
    settings = get_settings()
    return OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_request_timeout_s,
        num_ctx=settings.ollama_num_ctx,
    )


def get_llm_client() -> LLMClient:
    """FastAPI dependency. Overridden with a fake in tests."""
    return get_ollama_client()
