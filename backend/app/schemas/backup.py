from pydantic import BaseModel

from app.storage import BackendName
from app.storage.base import BackupInfo


class BackupCreateRequest(BaseModel):
    # Which backend to back up to; defaults to the server's configured
    # BACKUP_BACKEND when omitted, so existing clients that don't send a
    # body at all keep working unchanged.
    backend: BackendName | None = None


class BackupListResponse(BaseModel):
    backup_backend: str
    destination: str
    # Which backends this server can actually back up to right now -- local
    # is always usable; azure only once credentials are configured. Lets the
    # frontend show/hide the Azure option without guessing.
    available_backends: list[BackendName]
    backups: list[BackupInfo]


class RestoreRequest(BaseModel):
    name: str
    confirm: bool = False
    backend: BackendName | None = None


class RestoreResponse(BaseModel):
    restored_count: int
