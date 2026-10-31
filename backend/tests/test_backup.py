"""Service-level backup/restore tests (SPEC.md §9.1: LocalStorage + tmp_path,
no real Azure/MariaDB) plus the API-level flows (confirm required, 404 for
unknown backups, health never leaking secrets)."""

import json

import pytest

from app.enums import Category, Condition, SpecsSource
from app.models import Component
from app.services.backup import BackupRestoreError, create_backup, list_backups, restore_backup
from app.storage.local import LocalStorage


def insert_component(db, *, name="AMD Ryzen 5 3600", category=Category.CPU, quantity=1) -> Component:
    component = Component(
        category=category,
        name=name,
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


def test_restore_rejects_tampered_hash(db_session, tmp_path):
    insert_component(db_session, name="Original component")
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = json.loads(storage.download(info.name))
    snapshot["components"][0]["name"] = "Tampered name"  # sha256 now stale
    storage.upload(info.name, json.dumps(snapshot).encode("utf-8"))

    with pytest.raises(BackupRestoreError, match="sha256"):
        restore_backup(db_session, storage, info.name)

    # Nothing was touched.
    assert db_session.query(Component).one().name == "Original component"


def test_restore_rejects_unknown_schema_version(db_session, tmp_path):
    insert_component(db_session)
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = json.loads(storage.download(info.name))
    snapshot["schema_version"] = 99
    storage.upload(info.name, json.dumps(snapshot).encode("utf-8"))

    with pytest.raises(BackupRestoreError, match="schema_version"):
        restore_backup(db_session, storage, info.name)


def test_restore_rejects_invalid_component_and_changes_nothing(db_session, tmp_path):
    insert_component(db_session, name="Untouched component")
    storage = LocalStorage(str(tmp_path))
    info = create_backup(db_session, storage)

    snapshot = json.loads(storage.download(info.name))
    del snapshot["components"][0]["category"]  # now invalid against ComponentRead
    snapshot["sha256"] = (
        __import__("hashlib")
        .sha256(json.dumps(snapshot["components"], sort_keys=True).encode("utf-8"))
        .hexdigest()
    )
    storage.upload(info.name, json.dumps(snapshot).encode("utf-8"))

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

    snapshot = json.loads(storage.download(info.name))
    snapshot["component_count"] = 99
    storage.upload(info.name, json.dumps(snapshot).encode("utf-8"))

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
