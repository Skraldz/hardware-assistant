from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.llm.client import LLMClient, get_llm_client
from app.routers import backup, components, recommend
from app.storage import get_backup_storage_dependency
from app.storage.base import BackupStorage

app = FastAPI(title="Hardware Assistant API")
app.include_router(components.router)
app.include_router(recommend.router)
app.include_router(backup.router)


def _backup_destination(settings: Settings) -> str:
    if settings.backup_backend == "azure":
        return settings.azure_backup_container
    return settings.local_backup_dir


@app.get("/api/health")
def health(
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    storage: BackupStorage = Depends(get_backup_storage_dependency),
) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    ollama_status = "ok" if llm_client.ping() else "error"

    try:
        storage.list()
        storage_status = "ok"
    except Exception:
        storage_status = "error"

    overall = "ok" if db_status == ollama_status == storage_status == "ok" else "degraded"
    settings = get_settings()
    return {
        "status": overall,
        "db": db_status,
        "ollama": ollama_status,
        "storage": storage_status,
        # Container name or folder only — never a connection string (SPEC.md §7.2.1).
        "backup_backend": settings.backup_backend,
        "backup_destination": _backup_destination(settings),
    }
