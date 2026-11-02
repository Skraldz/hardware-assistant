"""API tests for the Phase 3 endpoints that involve the LLM and/or SearXNG:
/api/components/search, /api/components/extract, /api/recommend. Every test
overrides get_llm_client / get_search_client — none of this hits a real
Ollama or SearXNG (SPEC.md §9.1)."""

from app.config import Settings
from app.llm.client import get_llm_client
from app.main import app
from app.schemas.search import SearchCandidate
from app.search.client import get_search_client
from app.search.page_fetch import get_page_fetcher
from tests.fixtures.fake_llm import FakeLLMClient, load_fixture
from tests.fixtures.fake_page_fetcher import FakePageFetcher
from tests.fixtures.fake_search import FakeSearchClient

RAM_PAYLOAD = {
    "name": "Corsair Vengeance 16GB DDR4-3000",
    "quantity": 1,
    "specs": {
        "category": "ram",
        "memory_type": "DDR4",
        "capacity_gb_per_module": 8,
        "modules": 2,
        "speed_mts": 3000,
        "form": "DIMM",
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

STORAGE_PAYLOAD = {
    "name": "Intel NVMe 1TB",
    "quantity": 1,
    "specs": {"category": "storage", "interface": "nvme", "capacity_gb": 1000, "form_factor": "m2_2280"},
}

PSU_PAYLOAD = {
    "name": "Corsair RM650x",
    "quantity": 1,
    "specs": {
        "category": "psu",
        "wattage_w": 650,
        "form_factor": "ATX",
        "pcie_power_connectors": ["8-pin", "8-pin"],
        "efficiency_rating": "80+ Gold",
    },
}

CASE_PAYLOAD = {
    "name": "NZXT H510",
    "quantity": 1,
    "specs": {
        "category": "case",
        "supported_form_factors": ["ATX", "mATX", "ITX"],
        "max_gpu_length_mm": 381,
        "max_cooler_height_mm": 165,
        "psu_form_factor": "ATX",
        "drive_bays_3_5": 2,
        "drive_bays_2_5": 2,
    },
}

COOLER_PAYLOAD = {
    "name": "AMD Wraith Stealth",
    "quantity": 1,
    "specs": {
        "category": "cooler",
        "type": "air",
        "supported_sockets": ["AM4"],
        "height_mm": 54,
        "tdp_rating_w": 65,
    },
}

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

MOTHERBOARD_PAYLOAD = {
    "name": "ASUS TUF B450M-PLUS GAMING",
    "quantity": 1,
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


def seed_compatible_inventory(client) -> None:
    for payload in (
        CPU_PAYLOAD,
        MOTHERBOARD_PAYLOAD,
        RAM_PAYLOAD,
        GPU_PAYLOAD,
        STORAGE_PAYLOAD,
        PSU_PAYLOAD,
        CASE_PAYLOAD,
        COOLER_PAYLOAD,
    ):
        response = client.post("/api/components", json=payload)
        assert response.status_code == 201


# --- /api/components/search ---


def test_search_returns_candidates(client):
    candidate = SearchCandidate(
        title="NVIDIA GeForce RTX 2060 SUPER", url="https://example.com", snippet="8GB GDDR6"
    )
    app.dependency_overrides[get_search_client] = lambda: FakeSearchClient([candidate])
    response = client.post("/api/components/search", json={"name": "rtx 2060 super"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "rtx 2060 super"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["title"] == "NVIDIA GeForce RTX 2060 SUPER"


def test_search_returns_404_when_searxng_finds_nothing(client):
    app.dependency_overrides[get_search_client] = lambda: FakeSearchClient([])
    response = client.post("/api/components/search", json={"name": "does not exist"})
    assert response.status_code == 404


def test_search_returns_400_when_web_lookup_disabled(client, monkeypatch):
    monkeypatch.setattr("app.routers.components.get_settings", lambda: Settings(enable_web_lookup=False))
    response = client.post("/api/components/search", json={"name": "rtx 2060 super"})
    assert response.status_code == 400


def test_search_returns_503_when_searxng_unavailable(client):
    app.dependency_overrides[get_search_client] = lambda: FakeSearchClient([], unavailable=True)
    response = client.post("/api/components/search", json={"name": "rtx 2060 super"})
    assert response.status_code == 503


# --- /api/components/extract ---


def test_extract_with_candidate_returns_specs_from_web_lookup(client):
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [load_fixture("valid_category_gpu.json"), load_fixture("valid_extract_gpu.json")]
    )
    response = client.post(
        "/api/components/extract",
        json={
            "name": "RTX 2060 SUPER",
            "candidate": {
                "title": "NVIDIA GeForce RTX 2060 SUPER specs",
                "url": "https://example.com",
                "snippet": "8GB GDDR6, 175W TDP",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["specs"]["category"] == "gpu"
    assert body["specs"]["vram_gb"] == 8
    assert body["specs_source"] == "web_lookup"
    assert body["llm_used"] == "ok"


def test_extract_merges_other_candidates_snippets_into_the_prompt(client):
    fake_client = FakeLLMClient(
        [load_fixture("valid_category_gpu.json"), load_fixture("valid_extract_gpu.json")]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake_client
    response = client.post(
        "/api/components/extract",
        json={
            "name": "RTX 4070",
            "candidate": {
                "title": "RTX 4070 launch article",
                "url": "https://a.example.com",
                "snippet": "Launched April 2023, built on a 5 nm process.",
            },
            "other_candidates": [
                {
                    "title": "RTX 4070 specs",
                    "url": "https://b.example.com",
                    "snippet": "12 GB GDDR6X, TDP 200W.",
                }
            ],
        },
    )

    assert response.status_code == 200
    specs_prompt = fake_client.prompts[1]
    assert "Launched April 2023" in specs_prompt
    assert "12 GB GDDR6X, TDP 200W" in specs_prompt


def test_extract_merges_fetched_page_text_ahead_of_the_short_snippets(client):
    """The snippet alone ("8GB GDDR6, 175W TDP") never mentions PCIe power
    connectors -- this asserts the fetched page's own text (which does) is
    what actually reaches the extraction prompt, not just the snippet."""
    fake_client = FakeLLMClient(
        [load_fixture("valid_category_gpu.json"), load_fixture("valid_extract_gpu.json")]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake_client
    fake_fetcher = FakePageFetcher("Full spec table:\nPCIe power connectors: 1x 8-pin\nLength: 229mm")
    app.dependency_overrides[get_page_fetcher] = lambda: fake_fetcher

    response = client.post(
        "/api/components/extract",
        json={
            "name": "RTX 2060 SUPER",
            "candidate": {
                "title": "NVIDIA GeForce RTX 2060 SUPER specs",
                "url": "https://example.com/rtx-2060-super",
                "snippet": "8GB GDDR6, 175W TDP",
            },
        },
    )

    assert response.status_code == 200
    specs_prompt = fake_client.prompts[1]
    assert "PCIe power connectors: 1x 8-pin" in specs_prompt
    assert fake_fetcher.fetched_urls == ["https://example.com/rtx-2060-super"]


def test_extract_falls_back_to_snippets_when_the_page_fetch_fails(client):
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [load_fixture("valid_category_gpu.json"), load_fixture("valid_extract_gpu.json")]
    )
    app.dependency_overrides[get_page_fetcher] = lambda: FakePageFetcher(None)

    response = client.post(
        "/api/components/extract",
        json={
            "name": "RTX 2060 SUPER",
            "candidate": {
                "title": "NVIDIA GeForce RTX 2060 SUPER specs",
                "url": "https://example.com",
                "snippet": "8GB GDDR6, 175W TDP",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["specs_source"] == "web_lookup"


def test_extract_without_candidate_when_web_lookup_enabled_returns_400(client):
    response = client.post("/api/components/extract", json={"name": "RTX 2060 SUPER"})
    assert response.status_code == 400


def test_extract_without_web_lookup_uses_llm_knowledge_directly(client, monkeypatch):
    monkeypatch.setattr("app.routers.components.get_settings", lambda: Settings(enable_web_lookup=False))
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [load_fixture("valid_category_gpu.json"), load_fixture("valid_extract_gpu.json")]
    )
    response = client.post("/api/components/extract", json={"name": "RTX 2060 SUPER"})
    assert response.status_code == 200
    assert response.json()["specs_source"] == "llm_extracted"


def test_extract_returns_422_when_llm_output_never_validates(client):
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [load_fixture("invalid_json.txt"), load_fixture("invalid_json.txt")]
    )
    response = client.post(
        "/api/components/extract",
        json={
            "name": "Mystery part",
            "candidate": {"title": "x", "url": "https://example.com", "snippet": "x"},
        },
    )
    assert response.status_code == 422


def test_extract_returns_422_when_ollama_unavailable(client):
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient([], unavailable=True)
    response = client.post(
        "/api/components/extract",
        json={
            "name": "Mystery part",
            "candidate": {"title": "x", "url": "https://example.com", "snippet": "x"},
        },
    )
    assert response.status_code == 422


def test_unhandled_exception_still_gets_cors_headers(client):
    """Starlette places ServerErrorMiddleware outside user middleware
    (including CORSMiddleware), so a truly unhandled exception would
    normally produce a 500 with no CORS header and the browser would just
    report a generic network failure. main.py's global exception handler
    exists specifically to prevent that."""

    class ExplodingLLMClient:
        def generate_structured(self, *, system, prompt, schema):
            raise RuntimeError("unexpected error in a dependency, not caught by call_llm_with_retry")

        def ping(self):
            return True

    app.dependency_overrides[get_llm_client] = lambda: ExplodingLLMClient()
    response = client.post(
        "/api/components/extract",
        headers={"Origin": "http://example.com"},
        json={
            "name": "x",
            "candidate": {"title": "t", "url": "https://example.com", "snippet": "s"},
        },
    )

    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "*"
    assert response.json()["detail"] == "An unexpected server error occurred."


# --- /api/recommend ---


def test_recommend_endpoint_returns_a_build(client):
    seed_compatible_inventory(client)
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [
            load_fixture("valid_requirements_headless_ai.json"),
            load_fixture("valid_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    response = client.post(
        "/api/recommend",
        json={
            "conversation": [{"role": "user", "content": "headless pc for local AI"}],
            "max_builds": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_used"]["interpret"] == "ok"
    assert body["llm_used"]["rank"] == "ok"
    assert len(body["builds"]) == 1
    assert body["missing"] == []
    assert "build" in body["assistant_message"].lower()


def test_recommend_endpoint_reports_missing_categories_for_empty_inventory(client):
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(
        [load_fixture("valid_requirements_generic.json"), load_fixture("valid_chat_reply.json")]
    )

    response = client.post(
        "/api/recommend",
        json={"conversation": [{"role": "user", "content": "some pc"}], "max_builds": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["builds"] == []
    assert set(body["missing"]) == {
        "cpu",
        "motherboard",
        "ram",
        "storage",
        "psu",
        "case",
        "cooler",
    }


def test_recommend_endpoint_passes_the_full_conversation_to_the_requirements_llm(client):
    seed_compatible_inventory(client)
    fake_client = FakeLLMClient(
        [
            load_fixture("valid_requirements_headless_ai.json"),
            load_fixture("valid_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    response = client.post(
        "/api/recommend",
        json={
            "conversation": [
                {"role": "user", "content": "headless pc for local AI"},
                {"role": "assistant", "content": "Found 1 compatible build."},
                {"role": "user", "content": "actually, make it as low-power as possible"},
            ],
            "max_builds": 3,
        },
    )

    assert response.status_code == 200
    requirements_prompt = fake_client.prompts[0]
    assert "headless pc for local AI" in requirements_prompt
    assert "actually, make it as low-power as possible" in requirements_prompt
    assert "user:" in requirements_prompt
    assert "assistant:" in requirements_prompt


def test_recommend_endpoint_rejects_an_empty_conversation(client):
    response = client.post("/api/recommend", json={"conversation": [], "max_builds": 3})

    assert response.status_code == 422
