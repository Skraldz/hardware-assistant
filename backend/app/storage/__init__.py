"""SPEC.md §7.2.1: this module is the ONLY place in the codebase that reads
`settings.backup_backend`. Routers and services depend only on the
`BackupStorage` protocol (dependency injection via FastAPI `Depends`), never
on `LocalStorage`/`AzureBlobStorage` directly.
"""

from functools import lru_cache

from app.config import Settings, get_settings
from app.storage.azure_blob import AzureBlobStorage
from app.storage.base import BackupStorage
from app.storage.local import LocalStorage


def get_backup_storage(settings: Settings) -> BackupStorage:
    if settings.backup_backend == "local":
        return LocalStorage(settings.local_backup_dir)
    return AzureBlobStorage.from_settings(settings)


@lru_cache
def _cached_backup_storage() -> BackupStorage:
    return get_backup_storage(get_settings())


def get_backup_storage_dependency() -> BackupStorage:
    """FastAPI dependency. Overridden in tests."""
    return _cached_backup_storage()
