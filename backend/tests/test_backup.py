"""Service-level backup/restore tests (SPEC.md §9.1: LocalStorage + tmp_path,
no real Azure/MariaDB) plus the API-level flows (confirm required, 404 for
unknown backups, health never leaking secrets)."""

import hashlib
import json

import pytest

from app.enums import Category, Condition, SpecsSource
from app.models import Component, SavedBuild
from app.services.backup import (
    BackupRestoreError,
    _read_xlsx,
    _write_xlsx,
    create_backup,
    list_backups,
    restore_backup,
)
from app.storage.local import LocalStorage


def insert_component(
    db,
    *,
    name="AMD Ryzen 5 3600",
    category=Category.CPU,
    quantity=1,
    release_year=None,
    source_url=None,
) -> Component:
    component = Component(
        category=category,
        name=name,
        release_year=release_year,
        source_url=source_url,
        quantity=quantity,
        condition=Condition.NEW,
        specs={"category": category.value},
        specs_source=SpecsSource.MANUAL,
        specs_verified=True,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


# --- service-level ---


def test_backup_roundtrip_restores_identical_inventory(db_session, tmp_path):
    insert_component(db_session, name="AMD Ryzen 5 3600")
    insert_component(db_session, name="RTX 2060", category=Category.GPU)
    storage = LocalStorage(str(tmp_path))

    info = create_backup(db_session, storage)
    assert info.component_count == 2

    # Simulate data loss, then a change, so restore must truly replace it.
    db_session.query(Component).delete()
    db_session.commit()
    insert_component(db_session, name="Something else entirely", category=Category.PSU)

    restored_count = restore_backup(db_session, storage, info.name)

    assert restored_count == 2
    names = {c.name for c in db_session.query(Component).all()}
    assert names == {"AMD Ryzen 5 3600", "RTX 2060"}


def test_backup_roundtrip_survives_categories_inserted_out_of_sheet_order(db_session, tmp_path):
    """Regression test for a real bug found via a live Azure restore: the
    sha256 hash is computed over export_snapshot's `ORDER BY id` list, but
    _write_xlsx groups rows into one sheet per category for readability, so
    _read_xlsx's reconstructed list comes back ordered by category/sheet
    instead. json.dumps's sort_keys only sorts each dict's own keys, never
    the list itself -- any inventory whose insertion order doesn't already
    happen to match Category's own enum order (CPU, MOTHERBOARD, RAM, GPU,
    STORAGE, PSU, CASE, COOLER) would previously fail this check on every
    single restore, despite nothing actually being corrupted. Insertion
    order here (PSU, CPU, GPU, MOTHERBOARD) is deliberately not that order."""
    insert_component(db_session, name="PSU first", category=Category.PSU)
    insert_component(db_session, name="CPU second", category=Category.CPU)
    insert_component(db_session, name="GPU third", category=Category.GPU)
    insert_component(db_session, name="Motherboard fourth", category=Category.MOTHERBOARD)
    storage = LocalStorage(str(tmp_path))

    info = create_backup(db_session, storage)

    db_session.query(Component).delete()
    db_session.commit()
    restored_count = restore_backup(db_session, storage, info.name)

    assert restored_count == 4
    names = {c.name for c in db_session.query(Component).all()}
    assert names == {"PSU first", "CPU second", "GPU third", "Motherboard fourth"}


def test_restore_preserves_release_year(db_session, tmp_path):
    """Regression test: restore_backup's Component(...) reconstruction
    didn't copy release_year, so every restored component silently got
    release_year=None regardless of what the backup file actually had --
    the same "a field was added to the model, but a sibling reconstruction
    site wasn't updated" bug class as the purpose column and
    _COMMON_COLUMNS fixes, here breaking every era-based recommend request
    (released_no_later_than/released_no_earlier_than, prefer_oldest/prefer_newest) for
    any inventory that had ever been through a restore."""
    insert_component(db_session, name="Old CPU", release_year=2008)
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    db_session.query(Component).delete()
    db_session.commit()
    restore_backup(db_session, storage, info.name)

    restored = db_session.query(Component).one()
    assert restored.release_year == 2008


def test_restore_preserves_source_url(db_session, tmp_path):
    """Same bug class as test_restore_preserves_release_year, guarded up
    front this time rather than after the fact: source_url is a top-level
    ComponentBase field, so it has to survive the export/restore round trip
    as well as create_component. Provenance that silently disappears on a
    restore is worse than no provenance, because the surviving components
    still look like they were verified against a page."""
    url = "https://www.techpowerup.com/gpu-specs/geforce-rtx-4070-ti-super.c4187"
    insert_component(db_session, name="RTX 4070 Ti SUPER", category=Category.GPU, source_url=url)
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    db_session.query(Component).delete()
    db_session.commit()
    restore_backup(db_session, storage, info.name)

    assert db_session.query(Component).one().source_url == url


def test_backup_roundtrip_restores_saved_builds_with_remapped_component_ids(db_session, tmp_path):
    cpu = insert_component(db_session, name="AMD Ryzen 5 3600")
    gpu = insert_component(db_session, name="RTX 2060", category=Category.GPU)
    db_session.add(
        SavedBuild(
            name="My gaming PC",
            components=[
                {"id": cpu.id, "category": "cpu", "name": cpu.name},
                {"id": gpu.id, "category": "gpu", "name": gpu.name},
            ],
            purpose="play Baldur's Gate 3 at max resolution and 60 FPS",
            reason="Meets the stated requirements.",
        )
    )
    db_session.commit()
    storage = LocalStorage(str(tmp_path))

    info = create_backup(db_session, storage)
    assert info.component_count == 2

    db_session.query(Component).delete()
    db_session.query(SavedBuild).delete()
    db_session.commit()

    restore_backup(db_session, storage, info.name)

    restored_build = db_session.query(SavedBuild).one()
    assert restored_build.name == "My gaming PC"
    assert restored_build.purpose == "play Baldur's Gate 3 at max resolution and 60 FPS"
    # The restored components get fresh ids (auto-increment) -- the build's
    # own component references must point at those new ids, not the old
    # (now-meaningless) ones from before the restore.
    restored_components = {c.name: c.id for c in db_session.query(Component).all()}
    build_component_ids = {c["id"] for c in restored_build.components}
    assert build_component_ids == set(restored_components.values())


def test_restore_rejects_invalid_build_and_changes_nothing(db_session, tmp_path):
    cpu = insert_component(db_session, name="Untouched component")
    db_session.add(
        SavedBuild(components=[{"id": cpu.id, "category": "cpu", "name": cpu.name}], completed=False)
    )
    db_session.commit()
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = _read_xlsx(storage.download(info.name))
    # A ComponentSummary missing its required fields -- invalid against
    # SavedBuildRead's nested schema.
    snapshot["builds"][0]["components"] = [{"id": 999}]
    storage.upload(info.name, _write_xlsx(snapshot))

    with pytest.raises(BackupRestoreError, match="Invalid saved build"):
        restore_backup(db_session, storage, info.name)

    assert db_session.query(Component).one().name == "Untouched component"
    assert db_session.query(SavedBuild).count() == 1


def test_restore_still_works_for_a_legacy_json_backup_without_a_builds_key(db_session, tmp_path):
    insert_component(db_session, name="Legacy component")
    storage = LocalStorage(str(tmp_path))
    snapshot = {
        "schema_version": 1,
        "created_at": "2026-01-01T00:00:00",
        "app_version": "0.1.0",
        "component_count": 1,
        "components": [
            {
                "id": 1,
                "name": "Legacy component",
                "manufacturer": None,
                "quantity": 1,
                "condition": "new",
                "specs_source": "manual",
                "specs_verified": True,
                "notes": None,
                "category": "cpu",
                "specs": {"category": "cpu"},
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
    }
    snapshot["sha256"] = hashlib.sha256(
        json.dumps(snapshot["components"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    storage.upload("inventory-20260101T000000Z.json", json.dumps(snapshot).encode("utf-8"))

    restored_count = restore_backup(db_session, storage, "inventory-20260101T000000Z.json")

    assert restored_count == 1
    assert db_session.query(SavedBuild).count() == 0


def test_restore_rejects_tampered_hash(db_session, tmp_path):
    insert_component(db_session, name="Original component")
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = _read_xlsx(storage.download(info.name))
    snapshot["components"][0]["name"] = "Tampered name"  # sha256 now stale
    storage.upload(info.name, _write_xlsx(snapshot))

    with pytest.raises(BackupRestoreError, match="sha256"):
        restore_backup(db_session, storage, info.name)

    # Nothing was touched.
    assert db_session.query(Component).one().name == "Original component"


def test_restore_rejects_unknown_schema_version(db_session, tmp_path):
    insert_component(db_session)
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = _read_xlsx(storage.download(info.name))
    snapshot["schema_version"] = 99
    storage.upload(info.name, _write_xlsx(snapshot))

    with pytest.raises(BackupRestoreError, match="schema_version"):
        restore_backup(db_session, storage, info.name)


def test_restore_rejects_invalid_component_and_changes_nothing(db_session, tmp_path):
    insert_component(db_session, name="Untouched component")
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = _read_xlsx(storage.download(info.name))
    snapshot["components"][0]["quantity"] = -1  # violates ComponentBase's quantity >= 0
    snapshot["sha256"] = hashlib.sha256(
        json.dumps(snapshot["components"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    storage.upload(info.name, _write_xlsx(snapshot))

    with pytest.raises(BackupRestoreError, match="Invalid component"):
        restore_backup(db_session, storage, info.name)

    assert db_session.query(Component).one().name == "Untouched component"


def test_restore_unknown_backup_name_raises_file_not_found(db_session, tmp_path):
    storage = LocalStorage(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        restore_backup(db_session, storage, "inventory-does-not-exist.json")


def test_restore_rejects_invalid_json(db_session, tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.upload("inventory-20260101T000000Z.json", b"not valid json {{{")

    with pytest.raises(BackupRestoreError, match="valid JSON"):
        restore_backup(db_session, storage, "inventory-20260101T000000Z.json")


def test_restore_rejects_component_count_mismatch(db_session, tmp_path):
    insert_component(db_session)
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = _read_xlsx(storage.download(info.name))
    snapshot["component_count"] = 99
    storage.upload(info.name, _write_xlsx(snapshot))

    with pytest.raises(BackupRestoreError, match="component_count"):
        restore_backup(db_session, storage, info.name)


def test_restore_rolls_back_on_unexpected_db_failure(db_session, tmp_path):
    insert_component(db_session, name="Untouched component")
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    def failing_commit():
        raise RuntimeError("simulated database failure")

    db_session.commit = failing_commit

    with pytest.raises(RuntimeError, match="simulated database failure"):
        restore_backup(db_session, storage, info.name)

    # restore_backup's except block already rolled back before re-raising.
    del db_session.commit  # drop the instance override, restoring the bound method
    assert db_session.query(Component).one().name == "Untouched component"


def test_list_backups_skips_unreadable_backup_gracefully(db_session, tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.upload("inventory-20260101T000000Z.json", b"not valid json {{{")

    backups = list_backups(storage)

    assert len(backups) == 1
    assert backups[0].component_count is None


def test_list_backups_reports_name_timestamp_count_and_size(db_session, tmp_path):
    insert_component(db_session)
    storage = LocalStorage(str(tmp_path))
    create_backup(db_session, storage)

    backups = list_backups(storage)

    assert len(backups) == 1
    assert backups[0].component_count == 1
    assert backups[0].size_bytes > 0
    assert backups[0].created_at is not None


# --- API-level ---


def test_create_backup_via_api(client):
    client.post(
        "/api/components",
        json={"name": "CPU", "specs": {"category": "cpu"}},
    )
    response = client.post("/api/backup")
    assert response.status_code == 201
    assert response.json()["component_count"] == 1


def test_list_backups_via_api_shows_destination_and_backend(client):
    client.post("/api/backup")
    response = client.get("/api/backup")
    assert response.status_code == 200
    body = response.json()
    assert body["backup_backend"] == "local"
    assert len(body["backups"]) == 1


def test_restore_without_confirm_returns_400(client):
    client.post("/api/backup")
    backups = client.get("/api/backup").json()["backups"]
    response = client.post("/api/backup/restore", json={"name": backups[0]["name"]})
    assert response.status_code == 400


def test_restore_unknown_backup_returns_404(client):
    response = client.post("/api/backup/restore", json={"name": "inventory-nope.json", "confirm": True})
    assert response.status_code == 404


def test_restore_via_api_replaces_inventory(client):
    client.post("/api/components", json={"name": "Keep me", "specs": {"category": "cpu"}})
    backup_name = client.post("/api/backup").json()["name"]
    client.post("/api/components", json={"name": "Added after backup", "specs": {"category": "gpu"}})

    response = client.post("/api/backup/restore", json={"name": backup_name, "confirm": True})
    assert response.status_code == 200
    assert response.json()["restored_count"] == 1

    names = {c["name"] for c in client.get("/api/components").json()}
    assert names == {"Keep me"}


def test_list_backups_reports_available_backends(client):
    response = client.get("/api/backup")
    assert response.status_code == 200
    # No AZURE_STORAGE_* configured for this test client -- only local.
    assert response.json()["available_backends"] == ["local"]


def test_create_backup_with_unavailable_azure_backend_returns_400(client):
    response = client.post("/api/backup", json={"backend": "azure"})
    assert response.status_code == 400
    assert "azure" in response.json()["detail"].lower()


def test_list_backups_with_unavailable_azure_backend_returns_400(client):
    response = client.get("/api/backup?backend=azure")
    assert response.status_code == 400


def test_restore_with_unavailable_azure_backend_returns_400(client):
    response = client.post(
        "/api/backup/restore", json={"name": "inventory-x.json", "confirm": True, "backend": "azure"}
    )
    assert response.status_code == 400


def test_create_backup_explicit_local_backend_matches_default(client):
    response = client.post("/api/backup", json={"backend": "local"})
    assert response.status_code == 201
