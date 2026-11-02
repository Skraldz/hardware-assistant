"""Schemas for the two-step hardware lookup flow:

    POST /api/components/search  {"name"}              -> candidate list
    POST /api/components/extract {"name", "candidate"?} -> specs to confirm

`candidate` is required when ENABLE_WEB_LOOKUP=true (the chosen SearXNG
result) and ignored when it's false (the LLM extracts from its own
knowledge of `name` alone). `other_candidates` (optional) are the rest of
that same search's results -- a single snippet is often too short to
contain every spec (see docs/ai-log.md), while the other results for the
same query frequently have the missing numbers in theirs, so the backend
merges all of them into the extraction context rather than using the
chosen one alone.
"""

from pydantic import BaseModel

from app.enums import Category, SpecsSource
from app.schemas.components import ComponentSpecs


class SearchCandidate(BaseModel):
    title: str
    url: str
    snippet: str


class SearchRequest(BaseModel):
    name: str


class SearchResponse(BaseModel):
    query: str
    candidates: list[SearchCandidate]


class ExtractRequest(BaseModel):
    name: str
    candidate: SearchCandidate | None = None
    other_candidates: list[SearchCandidate] = []


class ExtractedSpecsEnvelope(BaseModel):
    """Wraps the ComponentSpecs discriminated union so it has a JSON schema
    to hand to Ollama's structured-output `format` (a bare `Annotated[Union[...]]`
    type alias doesn't have `.model_json_schema()` of its own). Currently
    unused by /extract itself (see CategoryGuess below), kept for any other
    caller that wants a single schema covering every category."""

    specs: ComponentSpecs


class CategoryGuess(BaseModel):
    """First step of /api/components/extract: ask the LLM only for the
    category, using a tiny schema (a single enum field) that Ollama's
    structured-output grammar can satisfy reliably. The category then
    selects a flat, single-category schema (SPEC_CLASS_BY_CATEGORY) for the
    second call that actually extracts the fields."""

    category: Category


class ExtractResponse(BaseModel):
    name: str
    specs: ComponentSpecs
    release_year: int | None = None
    specs_source: SpecsSource
    llm_used: str
