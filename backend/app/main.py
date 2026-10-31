import logging
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings, get_settings
from app.db import get_db
from app.llm.client import LLMClient, get_llm_client
from app.routers import backup, builds, components, recommend
from app.storage import get_backup_storage_dependency
from app.storage.base import BackupStorage

logger = logging.getLogger(__name__)

app = FastAPI(title="Hardware Assistant API")


class CatchUnhandledExceptionsMiddleware(BaseHTTPMiddleware):
    """Turns a truly unanticipated exception into a plain 500 response
    instead of letting it propagate to Starlette's ServerErrorMiddleware.

    FastAPI special-cases a handler registered for the bare `Exception`
    type: it gets hoisted onto ServerErrorMiddleware, which Starlette always
    places *outside* user middleware (including CORSMiddleware below) — so
    such a handler's response would still be missing CORS headers, and the
    browser would report a generic network failure instead of the real
    error. A plain middleware added *before* CORSMiddleware (making it the
    inner one) catches the exception itself and returns an ordinary
    Response, which then flows back out through CORSMiddleware normally.
    (Known Ollama/SearXNG failures are already caught at the source and
    turned into a proper HTTPException; this is the net for anything else.)
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unexpected error during %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})


app.add_middleware(CatchUnhandledExceptionsMiddleware)

# The frontend is served from a different port than the backend (and the
# home server's LAN address isn't fixed), so this is a real cross-origin
# request. Not a public-internet deployment, so allowing any origin is an
# acceptable simplification here — documented in docs/architecture.md.
# Added *after* CatchUnhandledExceptionsMiddleware so CORS stays outermost
# and still decorates the responses that middleware produces.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(components.router)
app.include_router(recommend.router)
app.include_router(backup.router)
app.include_router(builds.router)


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
        # Lets the frontend know whether /api/components/search is usable
        # (ENABLE_WEB_LOOKUP=false means /extract must be called directly).
        "enable_web_lookup": settings.enable_web_lookup,
    }
