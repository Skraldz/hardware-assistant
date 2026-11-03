"""SPEC.md §7.2.1: this module is the ONLY place in the codebase that reads
`settings.backup_backend`. Routers and services depend only on the
`BackupStorage` protocol (dependency injection via FastAPI `Depends`), never
on `LocalStorage`/`AzureBlobStorage` directly.

Originally `BACKUP_BACKEND` picked a single backend fixed for the whole
deployment. The frontend now lets the user pick local-vs-Azure per backup
(create/list/restore each independently choose), so `get_backup_storage_for`
below constructs whichever backend is actually requested, with
`BACKUP_BACKEND` only setting the *default* when none is explicitly given.
"""

from functools import lru_cache
from typing import Literal

from app.config import Settings, get_settings
from app.storage.azure_blob import AzureBlobStorage
from app.storage.base import BackupStorage
from app.storage.local import LocalStorage

BackendName = Literal["local", "azure"]


class BackendUnavailableError(Exception):
    """The requested backup backend isn't usable (e.g. Azure chosen without
    AZURE_STORAGE_CONNECTION_STRING/AZURE_STORAGE_ACCOUNT_URL configured)."""


def is_azure_available(settings: Settings) -> bool:
    """Whether Azure can be used at all.

    Args:
        settings: Application settings.

    Returns:
        bool: True once either credential form is configured -- independently
            of which backend BACKUP_BACKEND defaults to.
    """
    return bool(settings.azure_storage_connection_string or settings.azure_storage_account_url)


def available_backends(settings: Settings) -> list[BackendName]:
    """Local is always usable; Azure only once credentials are configured --
    independently of which one BACKUP_BACKEND defaults to, so Azure can be
    configured as an optional *extra* destination without making it the
    deployment's default."""
    backends: list[BackendName] = ["local"]
    if is_azure_available(settings):
        backends.append("azure")
    return backends


def get_backup_storage_for(backend: BackendName, settings: Settings) -> BackupStorage:
    """Build the storage for one named backend.

    Args:
        backend: "local" or "azure".
        settings: Application settings.

    Returns:
        BackupStorage: The storage for that backend.

    Raises:
        BackendUnavailableError: Azure was asked for without credentials.
    """
    if backend == "local":
        return LocalStorage(settings.local_backup_dir)
    if not is_azure_available(settings):
        raise BackendUnavailableError(
            "Azure backup is not configured on this server "
            "(set AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL)."
        )
    return AzureBlobStorage.from_settings(settings)


def get_backup_storage(settings: Settings) -> BackupStorage:
    """Build the storage for the configured default backend.

    Args:
        settings: Application settings.

    Returns:
        BackupStorage: Storage for settings.backup_backend.
    """
    return get_backup_storage_for(settings.backup_backend, settings)


@lru_cache
def _cached_backup_storage() -> BackupStorage:
    """The default backend's storage, built once per process."""
    return get_backup_storage(get_settings())


def get_backup_storage_dependency() -> BackupStorage:
    """FastAPI dependency for the default (BACKUP_BACKEND) storage, used by
    GET /api/health. Overridden in tests."""
    return _cached_backup_storage()
