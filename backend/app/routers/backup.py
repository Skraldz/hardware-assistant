"""Endpoints for creating, listing and restoring backups.

The destination is chosen per request rather than fixed at deployment, so
the same server can write locally today and to Azure tomorrow.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas.backup import BackupCreateRequest, BackupListResponse, RestoreRequest, RestoreResponse
from app.services.backup import BackupRestoreError, create_backup, list_backups, restore_backup
from app.storage import BackendName, BackendUnavailableError, available_backends, get_backup_storage_for
from app.storage.base import BackupInfo, BackupStorage

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _destination(backend: BackendName, settings: Settings) -> str:
    """Describe where a backend writes, for display in the UI.

    Args:
        backend: "local" or "azure".
        settings: Application settings.

    Returns:
        str: The Azure container name, or the local directory path.
    """
    if backend == "azure":
        return settings.azure_backup_container
    return settings.local_backup_dir


def _resolve_backend(requested: BackendName | None, settings: Settings) -> tuple[BackendName, BackupStorage]:
    """Pick the backup backend for one request.

    Args:
        requested: The backend named by the caller, or None to use the
            configured default.
        settings: Application settings.

    Returns:
        tuple[BackendName, BackupStorage]: The resolved name and its storage.

    Raises:
        HTTPException: 400 when the requested backend is not usable, e.g.
            Azure without credentials configured.
    """
    backend = requested or settings.backup_backend
    try:
        storage = get_backup_storage_for(backend, settings)
    except BackendUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return backend, storage


@router.post("", response_model=BackupInfo, status_code=201)
def create_backup_endpoint(
    payload: BackupCreateRequest | None = None,
    db: Session = Depends(get_db),
) -> BackupInfo:
    """Write a backup of the whole inventory.

    Args:
        payload: Optionally names the destination; omitted uses the default.
        db: Database session.

    Returns:
        BackupInfo: Name, size and timestamp of the file written.
    """
    settings = get_settings()
    _backend, storage = _resolve_backend(payload.backend if payload else None, settings)
    return create_backup(db, storage)


@router.get("", response_model=BackupListResponse)
def list_backups_endpoint(
    backend: BackendName | None = Query(default=None),
) -> BackupListResponse:
    """List the backups available on one backend.

    Args:
        backend: Which backend to list; omitted uses the default.

    Returns:
        BackupListResponse: The backups, the resolved backend, its
            destination, and which backends are usable at all -- never any
            credentials.
    """
    settings = get_settings()
    resolved, storage = _resolve_backend(backend, settings)
    return BackupListResponse(
        backup_backend=resolved,
        destination=_destination(resolved, settings),
        available_backends=available_backends(settings),
        backups=list_backups(storage),
    )


@router.post("/restore", response_model=RestoreResponse)
def restore_backup_endpoint(
    payload: RestoreRequest,
    db: Session = Depends(get_db),
) -> RestoreResponse:
    """Replace the entire inventory from a backup.

    Verifies schema version, component count and sha256 before writing
    anything, then restores inside a single transaction: a corrupt or
    tampered file changes nothing.

    Args:
        payload: Backup name, confirm=True, and optionally the backend.
        db: Database session.

    Returns:
        RestoreResponse: How many components were restored.

    Raises:
        HTTPException: 400 when not confirmed or the file fails its integrity
            checks, 404 when no backup has that name.
    """
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm: true is required to restore a backup.")
    settings = get_settings()
    _backend, storage = _resolve_backend(payload.backend, settings)
    try:
        restored_count = restore_backup(db, storage, payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Backup '{payload.name}' does not exist.") from exc
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RestoreResponse(restored_count=restored_count)
