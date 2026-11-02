from unittest.mock import MagicMock

from app.config import Settings
from app.main import app
from app.storage import get_backup_storage_dependency

CPU_PAYLOAD = {
    "name": "AMD Ryzen 5 3600",
    "manufacturer": "AMD",
    "quantity": 1,
    "condition": "used",
    "specs": {
        "category": "cpu",
        "socket": "AM4",
        "cores": 6,
        "threads": 12,
        "tdp_w": 65,
        "integrated_graphics": False,
        "memory_type": ["DDR4"],
    },
}

MOTHERBOARD_PAYLOAD = {
    "name": "ASUS TUF B450M-PLUS GAMING",
    "manufacturer": "ASUS",
    "quantity": 1,
    "condition": "used",
    "specs": {
        "category": "motherboard",
        "socket": "AM4",
        "form_factor": "mATX",
        "memory_type": ["DDR4"],
        "memory_slots": 4,
        "max_memory_gb": 64,
        "m2_slots": 1,
        "sata_ports": 4,
        "pcie_x16_slots": 1,
    },
}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["ollama"] == "ok"
    assert body["storage"] == "ok"
    assert body["backup_backend"] == "local"
    assert body["enable_web_lookup"] is True
    assert "connection_string" not in str(body).lower()


def test_health_never_leaks_azure_connection_string(client, monkeypatch):
    secret = "AccountKey=super-secret-value-do-not-leak"
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(backup_backend="azure", azure_storage_connection_string=secret),
    )
    app.dependency_overrides[get_backup_storage_dependency] = lambda: MagicMock(list=lambda: [])

    response = client.get("/api/health")

    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["backup_backend"] == "azure"
    assert response.json()["backup_destination"] == "inventory-backups"


def test_create_component_sets_category_from_specs(client):
    response = client.post("/api/components", json=CPU_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "cpu"
    assert body["specs"]["socket"] == "AM4"
    assert body["specs_verified"] is False
    assert body["specs_source"] == "manual"
    assert "id" in body
    assert "created_at" in body


def test_create_component_with_partial_specs_allows_unknown_fields(client):
    payload = {
        "name": "Mystery CPU",
        "specs": {"category": "cpu", "socket": "AM4"},
    }
    response = client.post("/api/components", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["specs"]["cores"] is None
    assert body["specs"]["tdp_w"] is None


def test_create_component_rejects_negative_quantity(client):
    payload = {**CPU_PAYLOAD, "quantity": -1}
    response = client.post("/api/components", json=payload)
    assert response.status_code == 422


def test_create_component_rejects_unknown_category(client):
    payload = {
        "name": "Not a real category",
        "specs": {"category": "toaster"},
    }
    response = client.post("/api/components", json=payload)
    assert response.status_code == 422


def test_list_components_filters_by_category(client):
    client.post("/api/components", json=CPU_PAYLOAD)
    client.post("/api/components", json=MOTHERBOARD_PAYLOAD)

    response = client.get("/api/components", params={"category": "cpu"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == "cpu"


def test_list_components_without_filter_returns_all(client):
    client.post("/api/components", json=CPU_PAYLOAD)
    client.post("/api/components", json=MOTHERBOARD_PAYLOAD)

    response = client.get("/api/components")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_component_by_id(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()

    response = client.get(f"/api/components/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_component_returns_404(client):
    response = client.get("/api/components/9999")
    assert response.status_code == 404


def test_update_component_partial_fields(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()

    response = client.put(f"/api/components/{created['id']}", json={"quantity": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 5
    assert body["specs"]["socket"] == "AM4"


def test_update_component_can_change_category_via_specs(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()

    response = client.put(
        f"/api/components/{created['id']}",
        json={"specs": MOTHERBOARD_PAYLOAD["specs"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "motherboard"
    assert body["specs"]["form_factor"] == "mATX"


def test_update_missing_component_returns_404(client):
    response = client.put("/api/components/9999", json={"quantity": 5})
    assert response.status_code == 404


def test_delete_component(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()

    response = client.delete(f"/api/components/{created['id']}")
    assert response.status_code == 204

    response = client.get(f"/api/components/{created['id']}")
    assert response.status_code == 404


def test_delete_missing_component_returns_404(client):
    response = client.delete("/api/components/9999")
    assert response.status_code == 404


def test_clear_inventory_without_confirm_returns_400(client):
    client.post("/api/components", json=CPU_PAYLOAD)
    response = client.post("/api/components/clear", json={})
    assert response.status_code == 400
    assert client.get("/api/components").json() != []


def test_clear_inventory_deletes_components_and_saved_builds(client, db_session):
    from app.models import SavedBuild

    created = client.post("/api/components", json=CPU_PAYLOAD).json()
    db_session.add(
        SavedBuild(name="Test build", components=[{"id": created["id"], "category": "cpu", "name": "x"}])
    )
    db_session.commit()

    response = client.post("/api/components/clear", json={"confirm": True})

    assert response.status_code == 200
    body = response.json()
    assert body == {"deleted_components": 1, "deleted_builds": 1}
    assert client.get("/api/components").json() == []
    assert client.get("/api/builds").json() == []


def test_reseed_without_confirm_returns_400(client):
    response = client.post("/api/components/reseed", json={})
    assert response.status_code == 400
    assert client.get("/api/components").json() == []


def test_reseed_adds_seed_data_on_top_without_touching_existing_components(client):
    from app.seed import SEED_COMPONENTS

    created = client.post("/api/components", json={**CPU_PAYLOAD, "name": "Not a seed component"}).json()

    response = client.post("/api/components/reseed", json={"confirm": True})

    assert response.status_code == 200
    body = response.json()
    assert body == {"added": len(SEED_COMPONENTS), "skipped": 0}
    names = {c["name"] for c in client.get("/api/components").json()}
    assert "Not a seed component" in names
    assert client.get(f"/api/components/{created['id']}").status_code == 200


def test_reseed_twice_does_not_duplicate_rows(client):
    from app.seed import SEED_COMPONENTS

    client.post("/api/components/reseed", json={"confirm": True})
    response = client.post("/api/components/reseed", json={"confirm": True})

    assert response.json() == {"added": 0, "skipped": len(SEED_COMPONENTS)}
    assert len(client.get("/api/components").json()) == len(SEED_COMPONENTS)


def test_create_component_persists_release_year(client):
    """Regression test: create_component's Component(...) construction
    didn't pass release_year, so every manually added or web-extracted
    component silently got release_year=None -- which then failed every
    hard era bound and sorted last. Fourth occurrence of the same bug
    class as the purpose column, _COMMON_COLUMNS and restore_backup."""
    created = client.post("/api/components", json={**CPU_PAYLOAD, "release_year": 2019}).json()

    assert created["release_year"] == 2019
    assert client.get(f"/api/components/{created['id']}").json()["release_year"] == 2019


def test_update_component_can_change_release_year(client):
    created = client.post("/api/components", json={**CPU_PAYLOAD, "release_year": 2019}).json()

    response = client.put(f"/api/components/{created['id']}", json={"release_year": 2015})

    assert response.status_code == 200
    assert response.json()["release_year"] == 2015


def test_create_component_persists_source_url(client):
    """Guards the same site that dropped release_year: create_component
    builds Component(...) field by field, so a new ComponentBase field is
    silently discarded unless it is added here too. source_url is the
    provenance link shown in the inventory, so losing it means a component
    looks hand-entered when it was actually extracted from a page."""
    url = "https://www.techpowerup.com/gpu-specs/geforce-rtx-4070-ti-super.c4187"
    created = client.post("/api/components", json={**CPU_PAYLOAD, "source_url": url}).json()

    assert created["source_url"] == url
    assert client.get(f"/api/components/{created['id']}").json()["source_url"] == url


def test_create_component_without_source_url_defaults_to_null(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()

    assert created["source_url"] is None


def test_update_component_can_set_source_url(client):
    created = client.post("/api/components", json=CPU_PAYLOAD).json()
    url = "https://www.amd.com/en/products/cpu/amd-ryzen-5-3600"

    response = client.put(f"/api/components/{created['id']}", json={"source_url": url})

    assert response.status_code == 200
    assert response.json()["source_url"] == url
