"""Schemas for the recommend pipeline (SPEC.md §5): the LLM's ranking output,
and the API response shape returned by POST /api/recommend.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.compatibility.types import RuleStatus
from app.enums import Category

ConversationRole = Literal["user", "assistant"]


class ConversationMessage(BaseModel):
    role: ConversationRole
    content: str


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
    # The full conversation so far, oldest first, so the user can refine an
    # earlier ask ("actually, nothing more powerful than that") across
    # multiple turns instead of only getting one shot at a single prompt.
    # Assistant turns are included only as context for the requirements LLM;
    # at least the latest user message is required.
    conversation: list[ConversationMessage] = Field(min_length=1)
    max_builds: int | None = None


class RecommendResponse(BaseModel):
    builds: list[BuildResult]
    missing: list[Category]
    llm_used: LlmUsed
    # A short, deterministic natural-language summary of the result, meant
    # to be shown as the assistant's reply in a chat-style UI.
    assistant_message: str
