"""Generic validate-retry-fallback wrapper around an LLMClient call
(SPEC.md §2/§9.1): invalid output -> one retry with the validation error fed
back to the model -> deterministic fallback. The system must never crash or
return unverified data because of a bad LLM response.
"""

import json
import logging
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient, LLMUnavailableError

logger = logging.getLogger(__name__)

LlmCallStatus = Literal["ok", "retried", "fallback"]


def call_llm_with_retry[T: BaseModel](
    llm_client: LLMClient,
    *,
    system: str,
    build_prompt: Callable[[str | None], str],
    schema: type[T],
    fallback: T | None,
    validate: Callable[[T], None] | None = None,
    max_attempts: int = 2,
) -> tuple[T | None, LlmCallStatus]:
    """Call `llm_client`, validate the JSON response against `schema`, and
    retry once with the error fed back before giving up and returning
    `fallback`.

    `validate` lets callers add semantic checks beyond the Pydantic schema
    (e.g. "every build_id must be in the candidate list") — raise ValueError
    to trigger the same retry/fallback path as a schema violation.

    `fallback` may be `None` when there is no sensible default to fall back
    to (e.g. extracting specs for an unknown category) — the caller must
    then handle a `None` result itself, typically by surfacing an error
    instead of returning unverified data.
    """
    last_error: str | None = None

    for attempt in range(max_attempts):
        prompt = build_prompt(last_error)
        # Lets a sparse/wrong answer be diagnosed as "the source text didn't
        # have this info" vs. "the model had it and didn't use it" -- the
        # raw response alone (logged below) can't tell those apart.
        logger.info("Prompt for %s (attempt %d): %s", schema.__name__, attempt + 1, prompt)
        try:
            raw = llm_client.generate_structured(system=system, prompt=prompt, schema=schema)
        except LLMUnavailableError as exc:
            # A down/unreachable Ollama won't fix itself within this request —
            # go straight to fallback instead of burning the retry budget
            # (and the user's wait, mid-demo) on a call that will fail again.
            logger.warning("LLM unavailable, using fallback without further attempts: %s", exc)
            return fallback, "fallback"
        # A sparse-but-schema-valid response (e.g. every optional field left
        # null) never raises below, so it would otherwise leave no trace in
        # the logs at all -- log the raw text on every attempt, not just
        # failures, so "the model answered but the content was poor" is
        # distinguishable from "the model's output didn't even parse".
        logger.info("Raw LLM response for %s (attempt %d): %s", schema.__name__, attempt + 1, raw)
        try:
            data = json.loads(raw)
            parsed = schema.model_validate(data)
            if validate is not None:
                validate(parsed)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = str(exc)
            logger.warning("Invalid LLM response (attempt %d/%d): %s", attempt + 1, max_attempts, last_error)
            continue
        return parsed, ("ok" if attempt == 0 else "retried")

    logger.warning("LLM response invalid after %d attempts, using fallback.", max_attempts)
    return fallback, "fallback"


def combine_status(*statuses: LlmCallStatus) -> LlmCallStatus:
    """Collapses several LlmCallStatus values (e.g. from a multi-step flow
    like /api/components/extract's category-then-specs calls) into one,
    worst-first: any fallback wins, then any retry, else ok."""
    if "fallback" in statuses:
        return "fallback"
    if "retried" in statuses:
        return "retried"
    return "ok"
