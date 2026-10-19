from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.client import LLMClient, get_llm_client
from app.routers import components, recommend

app = FastAPI(title="Hardware Assistant API")
app.include_router(components.router)
app.include_router(recommend.router)


@app.get("/api/health")
def health(db: Session = Depends(get_db), llm_client: LLMClient = Depends(get_llm_client)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    ollama_status = "ok" if llm_client.ping() else "error"

    overall = "ok" if db_status == "ok" and ollama_status == "ok" else "degraded"
    return {"status": overall, "db": db_status, "ollama": ollama_status}
