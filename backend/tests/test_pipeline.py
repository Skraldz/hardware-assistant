from app.enums import Category, Condition, SpecsSource
from app.models import Component
from app.pipeline.recommend import deterministic_score, prefilter_candidates, recommend
from app.schemas.requirements import ProjectRequirements
from tests.fixtures.fake_llm import FakeLLMClient, load_fixture


def insert_component(db, *, category, name, specs, quantity=1, condition=Condition.NEW) -> Component:
    component = Component(
        category=category,
        name=name,
        quantity=quantity,
        condition=condition,
        specs=specs,
        specs_source=SpecsSource.MANUAL,
        specs_verified=True,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def seed_compatible_inventory(db) -> None:
    insert_component(
        db,
        category=Category.CPU,
        name="AMD Ryzen 5 3600",
        specs={
            "category": "cpu",
            "socket": "AM4",
            "cores": 6,
            "threads": 12,
            "tdp_w": 65,
            "integrated_graphics": False,
            "memory_type": ["DDR4"],
        },
    )
    insert_component(
        db,
        category=Category.MOTHERBOARD,
        name="ASUS TUF B450M-PLUS GAMING",
        specs={
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
    )
    insert_component(
        db,
        category=Category.RAM,
        name="Corsair Vengeance 16GB DDR4-3000",
        specs={
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "speed_mts": 3000,
            "form": "DIMM",
        },
    )
    insert_component(
        db,
        category=Category.GPU,
        name="NVIDIA GeForce RTX 2060 6GB",
        specs={
            "category": "gpu",
            "vram_gb": 6,
            "tdp_w": 160,
            "length_mm": 229,
            "pcie_power_connectors": ["8-pin"],
            "vendor": "nvidia",
        },
    )
    insert_component(
        db,
        category=Category.STORAGE,
        name="Intel NVMe 1TB",
        specs={"category": "storage", "interface": "nvme", "capacity_gb": 1000, "form_factor": "m2_2280"},
    )
    insert_component(
        db,
        category=Category.PSU,
        name="Corsair RM650x",
        specs={
            "category": "psu",
            "wattage_w": 650,
            "form_factor": "ATX",
            "pcie_power_connectors": ["8-pin", "8-pin"],
            "efficiency_rating": "80+ Gold",
        },
    )
    insert_component(
        db,
        category=Category.CASE,
        name="NZXT H510",
        specs={
            "category": "case",
            "supported_form_factors": ["ATX", "mATX", "ITX"],
            "max_gpu_length_mm": 381,
            "max_cooler_height_mm": 165,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 2,
            "drive_bays_2_5": 2,
        },
    )
    insert_component(
        db,
        category=Category.COOLER,
        name="AMD Wraith Stealth",
        specs={
            "category": "cooler",
            "type": "air",
            "supported_sockets": ["AM4"],
            "height_mm": 54,
            "tdp_rating_w": 65,
        },
    )


def test_headless_local_ai_scenario_produces_a_build(db_session):
    seed_compatible_inventory(db_session)
    client = FakeLLMClient(
        [load_fixture("valid_requirements_headless_ai.json"), load_fixture("valid_ranking.json")]
    )

    result = recommend(prompt="headless pc til lokal AI", max_builds=3, db=db_session, llm_client=client)

    assert result.llm_used.interpret == "ok"
    assert result.llm_used.rank == "ok"
    assert result.missing == []
    assert len(result.builds) == 1
    assert result.builds[0].reason == "Opfylder VRAM- og RAM-kravene med lavest effektforbrug."
    categories = {c.category for c in result.builds[0].components}
    assert Category.GPU in categories


def test_incompatible_inventory_produces_no_builds_and_no_ranking_call(db_session):
    insert_component(
        db_session,
        category=Category.CPU,
        name="AMD Ryzen 5 3600",
        specs={"category": "cpu", "socket": "AM4", "cores": 6, "tdp_w": 65, "integrated_graphics": False},
    )
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="Gigabyte Z790 AORUS ELITE",
        specs={"category": "motherboard", "socket": "LGA1700", "form_factor": "ATX"},
    )

    # Only one fixture queued: if the pipeline tried to call the LLM again
    # for ranking (it shouldn't, since there's nothing to rank),
    # FakeLLMClient would raise on the second call.
    client = FakeLLMClient([load_fixture("valid_requirements_generic.json")])

    result = recommend(prompt="noget pc", max_builds=3, db=db_session, llm_client=client)

    assert result.builds == []
    assert result.llm_used.interpret == "ok"


def test_llm_failures_fall_back_to_deterministic_scoring(db_session):
    seed_compatible_inventory(db_session)
    client = FakeLLMClient(
        [
            load_fixture("invalid_json.txt"),
            load_fixture("invalid_json.txt"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
        ]
    )

    result = recommend(prompt="noget pc", max_builds=3, db=db_session, llm_client=client)

    assert result.llm_used.interpret == "fallback"
    assert result.llm_used.rank == "fallback"
    assert len(result.builds) == 1
    assert result.builds[0].reason.startswith("Automatisk valgt")


def test_prefilter_excludes_zero_quantity_and_faulty(db_session):
    insert_component(
        db_session,
        category=Category.CPU,
        name="Out of stock CPU",
        specs={"category": "cpu"},
        quantity=0,
    )
    insert_component(
        db_session,
        category=Category.GPU,
        name="Broken GPU",
        specs={"category": "gpu"},
        quantity=1,
        condition=Condition.FAULTY,
    )
    insert_component(
        db_session, category=Category.RAM, name="Good RAM", specs={"category": "ram"}, quantity=2
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x"))

    assert Category.CPU not in candidates
    assert Category.GPU not in candidates
    assert len(candidates[Category.RAM]) == 1


def test_prefilter_applies_hard_minimum_vram(db_session):
    insert_component(
        db_session,
        category=Category.GPU,
        name="Small GPU",
        specs={"category": "gpu", "vram_gb": 6},
    )
    insert_component(
        db_session,
        category=Category.GPU,
        name="Big GPU",
        specs={"category": "gpu", "vram_gb": 12},
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", min_vram_gb=8))

    names = {c.name for c in candidates[Category.GPU]}
    assert names == {"Big GPU"}


def test_prefilter_applies_hard_minimum_ram(db_session):
    insert_component(
        db_session,
        category=Category.RAM,
        name="Small RAM",
        specs={"category": "ram", "capacity_gb_per_module": 4, "modules": 2},
    )
    insert_component(
        db_session,
        category=Category.RAM,
        name="Big RAM",
        specs={"category": "ram", "capacity_gb_per_module": 16, "modules": 2},
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", min_ram_gb=16))

    names = {c.name for c in candidates[Category.RAM]}
    assert names == {"Big RAM"}


def test_prefilter_applies_hard_minimum_storage(db_session):
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Small SSD",
        specs={"category": "storage", "capacity_gb": 250},
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Big SSD",
        specs={"category": "storage", "capacity_gb": 1000},
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", min_storage_gb=500))

    names = {c.name for c in candidates[Category.STORAGE]}
    assert names == {"Big SSD"}


def test_prefilter_applies_hard_minimum_cpu_cores(db_session):
    insert_component(
        db_session, category=Category.CPU, name="Dual core", specs={"category": "cpu", "cores": 2}
    )
    insert_component(
        db_session, category=Category.CPU, name="Octa core", specs={"category": "cpu", "cores": 8}
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", min_cpu_cores=6))

    names = {c.name for c in candidates[Category.CPU]}
    assert names == {"Octa core"}


def test_recommend_reports_missing_gpu_when_no_gpu_meets_min_vram(db_session):
    seed_compatible_inventory(db_session)  # includes only a 6GB GPU
    client = FakeLLMClient([load_fixture("valid_requirements_min_vram_too_high.json")])

    result = recommend(prompt="AI-træning med meget VRAM", max_builds=3, db=db_session, llm_client=client)

    assert result.builds == []
    assert Category.GPU in result.missing


def test_deterministic_score_prefers_lower_power_when_requested(db_session):
    seed_compatible_inventory(db_session)
    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x"))
    from app.compatibility.engine import generate_builds

    result = generate_builds(candidates)
    evaluation = result.builds[0]

    score_default = deterministic_score(evaluation, ProjectRequirements(use_case="x"))
    score_low_power = deterministic_score(
        evaluation, ProjectRequirements(use_case="x", prefer_low_power=True)
    )
    assert score_low_power < score_default


def test_deterministic_score_prefers_small_form_factor_when_requested():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_specs

    # A case that only fits ATX scores worse under this preference than one
    # that also fits ITX (SPEC.md's smallest form factor).
    atx_only_case = with_specs(compatible_build().case, supported_form_factors=["ATX"])
    evaluation = BuildEvaluation(build=compatible_build(case=atx_only_case), rule_results={})

    score_default = deterministic_score(evaluation, ProjectRequirements(use_case="x"))
    score_small_ff = deterministic_score(
        evaluation, ProjectRequirements(use_case="x", prefer_small_form_factor=True)
    )
    assert score_small_ff < score_default


def test_rank_builds_with_empty_pool_is_a_trivial_ok():
    from app.pipeline.recommend import rank_builds

    ranked, status = rank_builds([], ProjectRequirements(use_case="x"), FakeLLMClient([]))

    assert ranked == []
    assert status == "ok"
