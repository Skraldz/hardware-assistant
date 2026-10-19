from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm.client import LLMClient, get_llm_client
from app.pipeline.recommend import recommend
from app.schemas.builds import RecommendRequest, RecommendResponse

router = APIRouter(prefix="/api/recommend", tags=["recommend"])


@router.post("", response_model=RecommendResponse)
def recommend_builds(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> RecommendResponse:
    max_builds = payload.max_builds or get_settings().recommend_default_max_builds
    return recommend(prompt=payload.prompt, max_builds=max_builds, db=db, llm_client=llm_client)
