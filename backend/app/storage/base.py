"""The backup storage abstraction (SPEC.md §7.2)."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class BackupInfo(BaseModel):
    name: str
    created_at: datetime
    size_bytes: int
    # Cheap at the storage layer (filename/blob metadata only); the service
    # layer (services/backup.py) fills this in by reading the snapshot.
    component_count: int | None = None


class BackupStorage(Protocol):
    def upload(self, name: str, data: bytes) -> str: ...

    def list(self) -> list[BackupInfo]: ...

    def download(self, name: str) -> bytes: ...
