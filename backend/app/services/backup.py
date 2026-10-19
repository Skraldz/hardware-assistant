"""Backup/restore logic (SPEC.md §7.3): export the whole inventory as a
snapshot, upload it, list what's available, and restore one back — verifying
its hash and schema version first, validating every component, and applying
the restore as a single all-or-nothing operation.
"""

import hashlib
import json
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Component
from app.schemas.components import ComponentRead
from app.storage.base import BackupInfo, BackupStorage

SCHEMA_VERSION = 1
APP_VERSION = "0.1.0"


class BackupRestoreError(Exception):
    """A backup failed validation and was not restored. Nothing was changed."""


def _components_hash(components: list[dict]) -> str:
    canonical = json.dumps(components, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _backup_filename(created_at: datetime) -> str:
    return f"inventory-{created_at.strftime('%Y%m%dT%H%M%SZ')}.json"


def export_snapshot(db: Session) -> dict:
    components = [
        ComponentRead.model_validate(row).model_dump(mode="json")
        for row in db.query(Component).order_by(Component.id).all()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "app_version": APP_VERSION,
        "component_count": len(components),
        "sha256": _components_hash(components),
        "components": components,
    }


def create_backup(db: Session, storage: BackupStorage) -> BackupInfo:
    snapshot = export_snapshot(db)
    created_at = datetime.fromisoformat(snapshot["created_at"])
    name = _backup_filename(created_at)
    data = json.dumps(snapshot, indent=2).encode("utf-8")
    storage.upload(name, data)
    return BackupInfo(
        name=name,
        created_at=created_at,
        size_bytes=len(data),
        component_count=snapshot["component_count"],
    )


def list_backups(storage: BackupStorage) -> list[BackupInfo]:
    """Enriches the storage layer's bare listing with `component_count`,
    which requires reading each snapshot — acceptable for the handful of
    backups a single-user project like this one keeps."""
    enriched = []
    for info in storage.list():
        try:
            data = json.loads(storage.download(info.name))
            component_count = data.get("component_count")
        except (json.JSONDecodeError, OSError):
            component_count = None
        enriched.append(info.model_copy(update={"component_count": component_count}))
    return enriched


def restore_backup(db: Session, storage: BackupStorage, name: str) -> int:
    """Returns the number of components restored. Raises BackupRestoreError
    (invalid backup, nothing changed) or FileNotFoundError (unknown name)."""
    raw = storage.download(name)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BackupRestoreError(f"Backup-filen er ikke gyldig JSON: {exc}") from exc

    if data.get("schema_version") != SCHEMA_VERSION:
        raise BackupRestoreError(f"Ukendt schema_version: {data.get('schema_version')!r}")

    raw_components = data.get("components", [])
    if data.get("component_count") != len(raw_components):
        raise BackupRestoreError("component_count passer ikke med antallet af komponenter i filen.")

    expected_hash = data.get("sha256")
    if expected_hash != _components_hash(raw_components):
        raise BackupRestoreError(
            "Backup-filens sha256-hash matcher ikke indholdet — filen kan være korrumperet."
        )

    validated: list[ComponentRead] = []
    for index, item in enumerate(raw_components):
        try:
            validated.append(ComponentRead.model_validate(item))
        except ValidationError as exc:
            raise BackupRestoreError(f"Ugyldig komponent i backup (index {index}): {exc}") from exc

    try:
        db.query(Component).delete()
        for item in validated:
            db.add(
                Component(
                    category=item.category,
                    name=item.name,
                    manufacturer=item.manufacturer,
                    quantity=item.quantity,
                    condition=item.condition,
                    specs=item.specs.model_dump(mode="json"),
                    specs_source=item.specs_source,
                    specs_verified=item.specs_verified,
                    notes=item.notes,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return len(validated)
