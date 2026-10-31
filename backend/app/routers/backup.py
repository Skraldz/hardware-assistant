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
    if backend == "azure":
        return settings.azure_backup_container
    return settings.local_backup_dir


def _resolve_backend(requested: BackendName | None, settings: Settings) -> tuple[BackendName, BackupStorage]:
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
    settings = get_settings()
    _backend, storage = _resolve_backend(payload.backend if payload else None, settings)
    return create_backup(db, storage)


@router.get("", response_model=BackupListResponse)
def list_backups_endpoint(
    backend: BackendName | None = Query(default=None),
) -> BackupListResponse:
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
