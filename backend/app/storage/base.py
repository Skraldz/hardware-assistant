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
    """Where backups are written and read.

    Implemented by LocalStorage and AzureBlobStorage. Routers and services
    depend on this rather than on either concrete backend, which is what
    lets the destination be chosen per request -- and what lets every test
    run against a temporary directory instead of Azure.
    """

    def upload(self, name: str, data: bytes) -> str:
        """Write one backup file.

        Args:
            name: File or blob name.
            data: File contents.

        Returns:
            str: Where it was written, for display to the user.
        """
        ...

    def list(self) -> list[BackupInfo]:
        """List the available backups, newest first.

        Returns:
            list[BackupInfo]: Name, size and timestamp for each backup.
        """
        ...

    def download(self, name: str) -> bytes:
        """Read one backup file by name.

        Args:
            name: File or blob name.

        Returns:
            bytes: The file contents.

        Raises:
            FileNotFoundError: When no backup has that name.
        """
        ...
