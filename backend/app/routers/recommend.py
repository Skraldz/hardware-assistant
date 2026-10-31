from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm.client import LLMClient, get_llm_client
from app.pipeline.recommend import recommend
from app.schemas.builds import ConversationMessage, RecommendRequest, RecommendResponse

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


def _build_transcript(conversation: list[ConversationMessage]) -> str:
    """Flattens the conversation into a single transcript string so the
    existing single-prompt pipeline (SPEC.md §5 step 1) doesn't need to know
    about multi-turn chat at all -- it just sees a longer "project
    description" to interpret, same as a one-shot prompt."""
    return "\n".join(f"{m.role}: {m.content}" for m in conversation)


@router.post("", response_model=RecommendResponse)
def recommend_builds(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> RecommendResponse:
    max_builds = payload.max_builds or get_settings().recommend_default_max_builds
    transcript = _build_transcript(payload.conversation)
    return recommend(prompt=transcript, max_builds=max_builds, db=db, llm_client=llm_client)
