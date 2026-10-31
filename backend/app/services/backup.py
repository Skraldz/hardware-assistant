"""Backup/restore logic (SPEC.md §7.3): export the whole inventory and saved
builds as a spreadsheet, upload it, list what's available, and restore one
back — verifying its hash and schema version first, validating every
component/build, and applying the restore as a single all-or-nothing
operation.

Backups are .xlsx workbooks (openpyxl): one sheet per component category
plus a Builds sheet, so the file is directly readable/editable in a
spreadsheet, rather than a single flat JSON blob. Internally the workbook is
still built from (and parsed back into) the same plain-dict "snapshot" shape
SPEC.md §7.1 describes, so the integrity checks (hash, schema_version,
per-row validation) are unchanged from the original design; only the
on-disk encoding differs. Backups created before this change are still
readable -- _read_backup dispatches on the file extension.
"""

import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.enums import Category
from app.models import Component, SavedBuild
from app.schemas.builds import SavedBuildRead
from app.schemas.components import SPEC_CLASS_BY_CATEGORY, ComponentRead
from app.storage.base import BackupInfo, BackupStorage

SCHEMA_VERSION = 1
APP_VERSION = "0.1.0"

# Every ComponentRead field except "category" (implied by which sheet a row
# is on) and "specs" (the category-specific columns that follow these).
_COMMON_COLUMNS = [
    "id",
    "name",
    "manufacturer",
    "quantity",
    "condition",
    "specs_source",
    "specs_verified",
    "notes",
    "created_at",
    "updated_at",
]

_BUILD_COLUMNS = ["id", "name", "purpose", "reason", "completed", "created_at", "completed_at", "components"]


class BackupRestoreError(Exception):
    """A backup failed validation and was not restored. Nothing was changed."""


def _components_hash(components: list[dict]) -> str:
    canonical = json.dumps(components, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _backup_filename(created_at: datetime) -> str:
    return f"inventory-{created_at.strftime('%Y%m%dT%H%M%SZ')}.xlsx"


def _to_cell(value: object) -> object:
    # A list-valued spec field (e.g. memory_type, pcie_power_connectors)
    # can't be stored in a single Excel cell directly -- JSON-encode it, and
    # _from_cell reverses this on read. Everything else (str/int/bool/None)
    # is already a native Excel cell type.
    return json.dumps(value) if isinstance(value, list) else value


def _from_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _write_xlsx(snapshot: dict) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    meta_ws = wb.create_sheet("Metadata")
    for key in ("schema_version", "created_at", "app_version", "component_count", "sha256"):
        meta_ws.append([key, snapshot[key]])

    components_by_category: dict[str, list[dict]] = {}
    for item in snapshot["components"]:
        components_by_category.setdefault(item["category"], []).append(item)

    for category in Category:
        spec_cols = [f for f in SPEC_CLASS_BY_CATEGORY[category].model_fields if f != "category"]
        ws = wb.create_sheet(category.value)
        ws.append([*_COMMON_COLUMNS, *spec_cols])
        for item in components_by_category.get(category.value, []):
            specs = item["specs"]
            row = [_to_cell(item.get(col)) for col in _COMMON_COLUMNS]
            row += [_to_cell(specs.get(col)) for col in spec_cols]
            ws.append(row)

    builds_ws = wb.create_sheet("Builds")
    builds_ws.append(_BUILD_COLUMNS)
    for build in snapshot.get("builds", []):
        builds_ws.append(
            [
                build["id"],
                build["name"],
                build["purpose"],
                build["reason"],
                build["completed"],
                build["created_at"],
                build["completed_at"],
                json.dumps(build["components"]),
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _read_xlsx(data: bytes) -> dict:
    try:
        wb = load_workbook(BytesIO(data), data_only=True)
    except Exception as exc:  # openpyxl raises several exception types for a corrupt/non-xlsx file
        raise BackupRestoreError(f"Backup file is not a valid spreadsheet: {exc}") from exc

    meta: dict[str, object] = {}
    if "Metadata" in wb.sheetnames:
        for row in wb["Metadata"].iter_rows(values_only=True):
            if row and row[0] is not None:
                meta[row[0]] = row[1]

    components: list[dict] = []
    for category in Category:
        if category.value not in wb.sheetnames:
            continue
        rows = list(wb[category.value].iter_rows(values_only=True))
        if not rows:
            continue
        header, *data_rows = rows
        spec_cols = list(header[len(_COMMON_COLUMNS) :])
        for raw_row in data_rows:
            if raw_row[0] is None:
                continue
            values = dict(zip(header, raw_row, strict=True))
            component = {col: _from_cell(values[col]) for col in _COMMON_COLUMNS}
            component["category"] = category.value
            component["specs"] = {col: _from_cell(values[col]) for col in spec_cols}
            component["specs"]["category"] = category.value
            components.append(component)

    builds: list[dict] = []
    if "Builds" in wb.sheetnames:
        rows = list(wb["Builds"].iter_rows(values_only=True))
        if rows:
            header, *data_rows = rows
            for raw_row in data_rows:
                if raw_row[0] is None:
                    continue
                values = dict(zip(header, raw_row, strict=True))
                builds.append(
                    {
                        "id": values["id"],
                        "name": values["name"],
                        "purpose": values["purpose"],
                        "reason": values["reason"],
                        "completed": bool(values["completed"]),
                        "created_at": values["created_at"],
                        "completed_at": values["completed_at"],
                        "components": json.loads(values["components"]) if values["components"] else [],
                    }
                )

    return {
        "schema_version": meta.get("schema_version"),
        "created_at": meta.get("created_at"),
        "app_version": meta.get("app_version"),
        "component_count": meta.get("component_count"),
        "sha256": meta.get("sha256"),
        "components": components,
        "builds": builds,
    }


def _read_backup(raw: bytes, name: str) -> dict:
    """Backward compatible with backups created before the spreadsheet
    format (plain JSON, no "builds" key -- treated as no saved builds)."""
    if name.endswith(".json"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackupRestoreError(f"Backup file is not valid JSON: {exc}") from exc
        data.setdefault("builds", [])
        return data
    return _read_xlsx(raw)


def export_snapshot(db: Session) -> dict:
    components = [
        ComponentRead.model_validate(row).model_dump(mode="json")
        for row in db.query(Component).order_by(Component.id).all()
    ]
    builds = [
        SavedBuildRead.model_validate(row).model_dump(mode="json")
        for row in db.query(SavedBuild).order_by(SavedBuild.id).all()
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "app_version": APP_VERSION,
        "component_count": len(components),
        "sha256": _components_hash(components),
        "components": components,
        "builds": builds,
    }


def create_backup(db: Session, storage: BackupStorage) -> BackupInfo:
    snapshot = export_snapshot(db)
    created_at = datetime.fromisoformat(snapshot["created_at"])
    name = _backup_filename(created_at)
    data = _write_xlsx(snapshot)
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
            data = _read_backup(storage.download(info.name), info.name)
            component_count = data.get("component_count")
        except Exception:
            component_count = None
        enriched.append(info.model_copy(update={"component_count": component_count}))
    return enriched


def restore_backup(db: Session, storage: BackupStorage, name: str) -> int:
    """Returns the number of components restored. Raises BackupRestoreError
    (invalid backup, nothing changed) or FileNotFoundError (unknown name)."""
    raw = storage.download(name)
    data = _read_backup(raw, name)

    if data.get("schema_version") != SCHEMA_VERSION:
        raise BackupRestoreError(f"Unknown schema_version: {data.get('schema_version')!r}")

    raw_components = data.get("components", [])
    if data.get("component_count") != len(raw_components):
        raise BackupRestoreError("component_count does not match the number of components in the file.")

    expected_hash = data.get("sha256")
    if expected_hash != _components_hash(raw_components):
        raise BackupRestoreError(
            "The backup file's sha256 hash does not match its contents — the file may be corrupted."
        )

    validated: list[ComponentRead] = []
    for index, item in enumerate(raw_components):
        try:
            validated.append(ComponentRead.model_validate(item))
        except ValidationError as exc:
            raise BackupRestoreError(f"Invalid component in backup (index {index}): {exc}") from exc

    validated_builds: list[SavedBuildRead] = []
    for index, item in enumerate(data.get("builds", [])):
        try:
            validated_builds.append(SavedBuildRead.model_validate(item))
        except ValidationError as exc:
            raise BackupRestoreError(f"Invalid saved build in backup (index {index}): {exc}") from exc

    try:
        db.query(Component).delete()
        # A saved build's `components` reference component ids by the id
        # they had *before* this restore -- those ids aren't preserved
        # (the DB assigns fresh ones), so this tracks old id -> new id to
        # rewrite each restored build's component references afterwards.
        id_remap: dict[int, int] = {}
        for item in validated:
            component = Component(
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
            db.add(component)
            db.flush()
            id_remap[item.id] = component.id

        db.query(SavedBuild).delete()
        for build in validated_builds:
            remapped_components = [
                {**c.model_dump(mode="json"), "id": id_remap.get(c.id, c.id)} for c in build.components
            ]
            db.add(
                SavedBuild(
                    name=build.name,
                    components=remapped_components,
                    purpose=build.purpose,
                    reason=build.reason,
                    completed=build.completed,
                    completed_at=build.completed_at,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return len(validated)
