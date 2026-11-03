"""Request and response shapes for the backup endpoints."""

from pydantic import BaseModel

from app.storage import BackendName
from app.storage.base import BackupInfo


class BackupCreateRequest(BaseModel):
    """Which backend to back up to; omitted uses the configured default."""

    # Which backend to back up to; defaults to the server's configured
    # BACKUP_BACKEND when omitted, so existing clients that don't send a
    # body at all keep working unchanged.
    backend: BackendName | None = None


class BackupListResponse(BaseModel):
    """The available backups, plus which backends are usable at all.

    Carries the active backend and its destination so the UI can show where
    data goes -- but never any credential.
    """

    backup_backend: str
    destination: str
    # Which backends this server can actually back up to right now -- local
    # is always usable; azure only once credentials are configured. Lets the
    # frontend show/hide the Azure option without guessing.
    available_backends: list[BackendName]
    backups: list[BackupInfo]


class RestoreRequest(BaseModel):
    """Payload for replacing the inventory from a backup.

    `confirm` must be True: restoring overwrites everything currently
    stored.
    """

    name: str
    confirm: bool = False
    backend: BackendName | None = None


class RestoreResponse(BaseModel):
    """How many components the restore wrote."""

    restored_count: int
