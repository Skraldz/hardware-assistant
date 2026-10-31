from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas.backup import BackupListResponse, RestoreRequest, RestoreResponse
from app.services.backup import BackupRestoreError, create_backup, list_backups, restore_backup
from app.storage import get_backup_storage_dependency
from app.storage.base import BackupInfo, BackupStorage

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _destination(settings: Settings) -> str:
    if settings.backup_backend == "azure":
        return settings.azure_backup_container
    return settings.local_backup_dir


@router.post("", response_model=BackupInfo, status_code=201)
def create_backup_endpoint(
    db: Session = Depends(get_db),
    storage: BackupStorage = Depends(get_backup_storage_dependency),
) -> BackupInfo:
    return create_backup(db, storage)


@router.get("", response_model=BackupListResponse)
def list_backups_endpoint(
    storage: BackupStorage = Depends(get_backup_storage_dependency),
) -> BackupListResponse:
    settings = get_settings()
    return BackupListResponse(
        backup_backend=settings.backup_backend,
        destination=_destination(settings),
        backups=list_backups(storage),
    )


@router.post("/restore", response_model=RestoreResponse)
def restore_backup_endpoint(
    payload: RestoreRequest,
    db: Session = Depends(get_db),
    storage: BackupStorage = Depends(get_backup_storage_dependency),
) -> RestoreResponse:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm: true is required to restore a backup.")
    try:
        restored_count = restore_backup(db, storage, payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Backup '{payload.name}' does not exist.") from exc
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RestoreResponse(restored_count=restored_count)
