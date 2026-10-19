from pydantic import BaseModel

from app.storage.base import BackupInfo


class BackupListResponse(BaseModel):
    backup_backend: str
    destination: str
    backups: list[BackupInfo]


class RestoreRequest(BaseModel):
    name: str
    confirm: bool = False


class RestoreResponse(BaseModel):
    restored_count: int
