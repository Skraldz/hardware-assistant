"""Schemas for the two-step hardware lookup flow:

    POST /api/components/search  {"name"}              -> candidate list
    POST /api/components/extract {"name", "candidate"?} -> specs to confirm

`candidate` is required when ENABLE_WEB_LOOKUP=true (the chosen SearXNG
result) and ignored when it's false (the LLM extracts from its own
knowledge of `name` alone).
"""

from pydantic import BaseModel

from app.enums import SpecsSource
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


class ExtractedSpecsEnvelope(BaseModel):
    """Wraps the ComponentSpecs discriminated union so it has a JSON schema
    to hand to Ollama's structured-output `format` (a bare `Annotated[Union[...]]`
    type alias doesn't have `.model_json_schema()` of its own)."""

    specs: ComponentSpecs


class ExtractResponse(BaseModel):
    name: str
    specs: ComponentSpecs
    specs_source: SpecsSource
    llm_used: str
