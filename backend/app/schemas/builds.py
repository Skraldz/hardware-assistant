"""Schemas for the recommend pipeline (SPEC.md §5): the LLM's ranking output,
the API response shape returned by POST /api/recommend, and the saved/
completed builds exposed by routers/builds.py's "Builds" tab.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ChatReply(BaseModel):
    # A free-text reply to the user's latest message, written with the
    # already-computed builds as context (pipeline/recommend.py's
    # generate_chat_reply) -- e.g. actually answering "what model can I run
    # on these?" instead of just restating that builds were found.
    reply: str


class RuleResultOut(BaseModel):
    status: RuleStatus
    message: str


class ComponentSummary(BaseModel):
    id: int
    category: Category
    name: str
    release_year: int | None = None


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
    reply: LlmCallStatus


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
    # The assistant's reply to the user's latest message, shown in the
    # chat-style UI -- written by generate_chat_reply() with the computed
    # builds as context (falling back to a deterministic summary if that
    # LLM call is unavailable or invalid).
    assistant_message: str


class SavedBuildCreate(BaseModel):
    name: str | None = None
    components: list[ComponentSummary] = Field(min_length=1)
    # Why the user wanted this build in the first place (e.g. "play
    # Baldur's Gate 3 at max resolution and 60 FPS") -- distinct from
    # `reason`, which is the ranking LLM's justification for picking this
    # build over the other candidates it was given.
    purpose: str | None = None
    reason: str | None = None


class SavedBuildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    components: list[ComponentSummary]
    purpose: str | None
    reason: str | None
    completed: bool
    created_at: datetime
    completed_at: datetime | None


class CompleteBuildResponse(BaseModel):
    id: int
    completed: bool
    # Ids of components whose inventory quantity was actually decremented --
    # a component already deleted, or already at quantity 0 (e.g. used by an
    # earlier completed build), is skipped rather than erroring.
    removed_component_ids: list[int]
