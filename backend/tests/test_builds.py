"""Tests for the "Builds" tab (save a recommended build, mark it complete --
which decrements the inventory quantity of each component it used). No LLM
involved (SPEC.md §9.1): these endpoints only touch the database."""

CPU_PAYLOAD = {
    "name": "AMD Ryzen 5 3600",
    "quantity": 1,
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

GPU_PAYLOAD = {
    "name": "NVIDIA GeForce RTX 2060 6GB",
    "quantity": 1,
    "specs": {
        "category": "gpu",
        "vram_gb": 6,
        "tdp_w": 160,
        "length_mm": 229,
        "pcie_power_connectors": ["8-pin"],
        "vendor": "nvidia",
    },
}


def create_component(client, payload):
    response = client.post("/api/components", json=payload)
    assert response.status_code == 201
    return response.json()


def test_save_build_returns_it_and_list_includes_it(client):
    cpu = create_component(client, CPU_PAYLOAD)

    response = client.post(
        "/api/builds",
        json={
            "name": "My headless AI box",
            "components": [{"id": cpu["id"], "category": "cpu", "name": cpu["name"]}],
            "purpose": "play Baldur's Gate 3 at max resolution and 60 FPS",
            "reason": "Meets the requirements.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My headless AI box"
    assert body["purpose"] == "play Baldur's Gate 3 at max resolution and 60 FPS"
    assert body["reason"] == "Meets the requirements."
    assert body["completed"] is False
    assert body["completed_at"] is None
    assert body["components"] == [{"id": cpu["id"], "category": "cpu", "name": cpu["name"]}]

    listed = client.get("/api/builds").json()
    assert listed[0]["purpose"] == "play Baldur's Gate 3 at max resolution and 60 FPS"

    listed = client.get("/api/builds")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_save_build_requires_at_least_one_component(client):
    response = client.post("/api/builds", json={"components": []})
    assert response.status_code == 422


def test_complete_build_decrements_component_quantity(client):
    cpu = create_component(client, CPU_PAYLOAD)
    gpu = create_component(client, GPU_PAYLOAD)
    saved = client.post(
        "/api/builds",
        json={
            "components": [
                {"id": cpu["id"], "category": "cpu", "name": cpu["name"]},
                {"id": gpu["id"], "category": "gpu", "name": gpu["name"]},
            ]
        },
    ).json()

    response = client.post(f"/api/builds/{saved['id']}/complete")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert set(body["removed_component_ids"]) == {cpu["id"], gpu["id"]}

    assert client.get(f"/api/components/{cpu['id']}").json()["quantity"] == 0
    assert client.get(f"/api/components/{gpu['id']}").json()["quantity"] == 0

    listed = client.get("/api/builds").json()
    assert listed[0]["completed"] is True
    assert listed[0]["completed_at"] is not None


def test_complete_build_skips_components_already_deleted_or_out_of_stock(client):
    cpu = create_component(client, CPU_PAYLOAD)
    saved = client.post(
        "/api/builds",
        json={"components": [{"id": cpu["id"], "category": "cpu", "name": cpu["name"]}]},
    ).json()
    client.delete(f"/api/components/{cpu['id']}")

    response = client.post(f"/api/builds/{saved['id']}/complete")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert body["removed_component_ids"] == []


def test_complete_build_twice_returns_400(client):
    cpu = create_component(client, CPU_PAYLOAD)
    saved = client.post(
        "/api/builds",
        json={"components": [{"id": cpu["id"], "category": "cpu", "name": cpu["name"]}]},
    ).json()
    client.post(f"/api/builds/{saved['id']}/complete")

    response = client.post(f"/api/builds/{saved['id']}/complete")

    assert response.status_code == 400


def test_complete_unknown_build_returns_404(client):
    response = client.post("/api/builds/999/complete")
    assert response.status_code == 404


def test_delete_build_removes_it_but_not_the_components(client):
    cpu = create_component(client, CPU_PAYLOAD)
    saved = client.post(
        "/api/builds",
        json={"components": [{"id": cpu["id"], "category": "cpu", "name": cpu["name"]}]},
    ).json()

    response = client.delete(f"/api/builds/{saved['id']}")

    assert response.status_code == 204
    assert client.get("/api/builds").json() == []
    assert client.get(f"/api/components/{cpu['id']}").status_code == 200


def test_delete_unknown_build_returns_404(client):
    response = client.delete("/api/builds/999")
    assert response.status_code == 404
