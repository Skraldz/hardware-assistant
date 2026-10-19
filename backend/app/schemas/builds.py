"""Schemas for the recommend pipeline (SPEC.md §5): the LLM's ranking output,
and the API response shape returned by POST /api/recommend.
"""

from typing import Literal

from pydantic import BaseModel

from app.compatibility.types import RuleStatus
from app.enums import Category


class BuildRankingEntry(BaseModel):
    build_id: int
    reason: str


class BuildRanking(BaseModel):
    ranking: list[BuildRankingEntry]


class RuleResultOut(BaseModel):
    status: RuleStatus
    message: str


class ComponentSummary(BaseModel):
    id: int
    category: Category
    name: str


class BuildResult(BaseModel):
    components: list[ComponentSummary]
    rule_results: dict[str, RuleResultOut]
    warnings: list[str]
    reason: str
    score: float


LlmCallStatus = Literal["ok", "retried", "fallback"]


class LlmUsed(BaseModel):
    interpret: LlmCallStatus
    rank: LlmCallStatus


class RecommendRequest(BaseModel):
    prompt: str
    max_builds: int | None = None


class RecommendResponse(BaseModel):
    builds: list[BuildResult]
    missing: list[Category]
    llm_used: LlmUsed
