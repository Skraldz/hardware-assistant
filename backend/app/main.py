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

# Uvicorn doesn't touch the root logger's level by default, so without this
# every plain logger.info(...) call in the app (e.g. llm/parsing.py's raw
# LLM response logging, useful for diagnosing "the model answered but the
# content was poor") is silently dropped at the default WARNING level.
logging.basicConfig(level=logging.INFO)

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

# Only loopback and RFC1918 origins, on any port. The frontend is served
# from a different port than the backend and derives the API URL from
# window.location.hostname, so the legitimate origin varies with whichever
# address the user typed -- but it is always on their own network.
#
# This used to be allow_origins=["*"], justified as "not a public-internet
# deployment". That reasoning has a hole: with no authentication on any
# endpoint, the wildcard let any website the user visited read the whole
# inventory and wipe it with a single POST to /api/components/clear. The
# attacker never needed network access; the victim's browser already had it,
# and "*" is exactly what made the response readable cross-origin.
#
# DNS rebinding does not get around this: the Origin header carries the
# attacker's own hostname, never the address it resolved to.
_PRIVATE_ORIGIN_REGEX = (
    r"https?://("
    r"localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\]"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?"
)


def _cors_kwargs(settings: Settings) -> dict:
    """An explicit CORS_ALLOW_ORIGINS list wins; otherwise fall back to the
    private-network regex. Credentials stay off -- the API uses no cookies,
    and allow_credentials with a permissive origin rule is what turns a
    readable response into a session-riding one."""
    configured = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    origins = {"allow_origins": configured} if configured else {"allow_origin_regex": _PRIVATE_ORIGIN_REGEX}
    return {**origins, "allow_methods": ["*"], "allow_headers": ["*"]}


# Added *after* CatchUnhandledExceptionsMiddleware so CORS stays outermost
# and still decorates the responses that middleware produces.
app.add_middleware(CORSMiddleware, **_cors_kwargs(get_settings()))

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
