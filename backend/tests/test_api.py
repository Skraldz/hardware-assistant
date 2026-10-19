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
