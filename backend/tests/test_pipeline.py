from app.enums import Category, Condition, SpecsSource
from app.models import Component
from app.pipeline.recommend import (
    _select_diverse_builds,
    deterministic_score,
    prefilter_candidates,
    recommend,
)
from app.schemas.requirements import ProjectRequirements
from tests.fixtures.fake_llm import FakeLLMClient, load_fixture


def insert_component(
    db, *, category, name, specs, quantity=1, condition=Condition.NEW, release_year=None
) -> Component:
    component = Component(
        category=category,
        name=name,
        release_year=release_year,
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
        [
            load_fixture("valid_requirements_headless_ai.json"),
            load_fixture("valid_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="headless pc for local AI", max_builds=3, db=db_session, llm_client=client)

    assert result.llm_used.interpret == "ok"
    assert result.llm_used.rank == "ok"
    assert result.missing == []
    assert len(result.builds) == 1
    assert result.builds[0].reason == "Meets the VRAM and RAM requirements with the lowest power draw."
    categories = {c.category for c in result.builds[0].components}
    assert Category.GPU in categories


def test_chat_reply_prompt_includes_actual_build_specs(db_session):
    seed_compatible_inventory(db_session)
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_headless_ai.json"),
            load_fixture("valid_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    recommend(prompt="headless pc for local AI", max_builds=3, db=db_session, llm_client=client)

    chat_reply_prompt = client.prompts[-1]
    assert "'vram_gb': 6" in chat_reply_prompt
    assert "'cores'" in chat_reply_prompt


def test_clarifying_question_is_surfaced_in_the_assistant_message(db_session):
    seed_compatible_inventory(db_session)
    # The chat-reply call is forced to fall back (two invalid responses), so
    # the assistant_message comes from the deterministic fallback, which is
    # the one place that appends requirements.clarifying_question.
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_needs_clarification.json"),
            load_fixture("valid_ranking.json"),
            load_fixture("invalid_json.txt"),
            load_fixture("invalid_json.txt"),
        ]
    )

    result = recommend(prompt="a new pc", max_builds=3, db=db_session, llm_client=client)

    assert "What will you mainly use this PC for" in result.assistant_message
    assert result.llm_used.reply == "fallback"


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

    # Two fixtures: requirements interpretation, then the chat reply. If the
    # pipeline tried to call the LLM for ranking too (it shouldn't, since
    # there's nothing to rank), FakeLLMClient would raise on a third call.
    client = FakeLLMClient(
        [load_fixture("valid_requirements_generic.json"), load_fixture("valid_chat_reply.json")]
    )

    result = recommend(prompt="some pc", max_builds=3, db=db_session, llm_client=client)

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
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="some pc", max_builds=3, db=db_session, llm_client=client)

    assert result.llm_used.interpret == "fallback"
    assert result.llm_used.rank == "fallback"
    assert len(result.builds) == 1
    assert result.builds[0].reason.startswith("Automatically selected")


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
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_min_vram_too_high.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="AI training with lots of VRAM", max_builds=3, db=db_session, llm_client=client)

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


def test_deterministic_score_gently_prefers_lower_power_even_without_the_preference():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_specs

    low_tdp = BuildEvaluation(
        build=compatible_build(cpu=with_specs(compatible_build().cpu, tdp_w=65)), rule_results={}
    )
    high_tdp = BuildEvaluation(
        build=compatible_build(cpu=with_specs(compatible_build().cpu, tdp_w=125)), rule_results={}
    )

    requirements = ProjectRequirements(use_case="x")
    assert deterministic_score(low_tdp, requirements) > deterministic_score(high_tdp, requirements)


def test_deterministic_score_does_not_penalize_vram_without_a_stated_minimum():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, gpu_rtx_2060, with_specs

    # Same build except for GPU VRAM -- with no min_vram_gb requested at
    # all, a bigger GPU should not score worse just for existing.
    modest = BuildEvaluation(
        build=compatible_build(gpu=with_specs(gpu_rtx_2060(), vram_gb=6, tdp_w=160)), rule_results={}
    )
    big = BuildEvaluation(
        build=compatible_build(gpu=with_specs(gpu_rtx_2060(), vram_gb=24, tdp_w=160)), rule_results={}
    )

    requirements = ProjectRequirements(use_case="x")
    assert deterministic_score(modest, requirements) == deterministic_score(big, requirements)


def test_deterministic_score_prefers_minimal_spec_when_requested():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_specs

    # compatible_build()'s default GPU has 6 GB VRAM; a build with a much
    # bigger GPU should score worse once prefer_minimal_spec is set and a
    # modest min_vram_gb is already comfortably met.
    big_gpu_build = compatible_build(gpu=with_specs(compatible_build().gpu, vram_gb=16))
    big_gpu_evaluation = BuildEvaluation(build=big_gpu_build, rule_results={})
    baseline_evaluation = BuildEvaluation(build=compatible_build(), rule_results={})

    requirements = ProjectRequirements(use_case="x", min_vram_gb=2, prefer_minimal_spec=True)
    score_big = deterministic_score(big_gpu_evaluation, requirements)
    score_modest = deterministic_score(baseline_evaluation, requirements)
    assert score_big < score_modest


def test_crysis_style_prompt_prefers_the_smaller_sufficient_gpu(db_session):
    """'I need a pc that can run Crysis 1 at max resolution, but not more
    powerful than that' -- the LLM is expected to infer modest minimums
    (min_vram_gb=2, min_cpu_cores=2) and set prefer_minimal_spec=true (see
    the fixture); with ranking forced to fallback, the deterministic scorer
    should pick the smallest GPU that still clears the minimum over a
    massively overpowered one."""
    insert_component(
        db_session,
        category=Category.CPU,
        name="Budget quad-core",
        specs={
            "category": "cpu",
            "socket": "AM4",
            "cores": 4,
            "tdp_w": 65,
            "integrated_graphics": False,
            "memory_type": ["DDR4"],
        },
    )
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="Budget AM4 board",
        specs={
            "category": "motherboard",
            "socket": "AM4",
            "form_factor": "ATX",
            "memory_type": ["DDR4"],
            "memory_slots": 4,
            "max_memory_gb": 64,
            "m2_slots": 1,
            "sata_ports": 4,
        },
    )
    insert_component(
        db_session,
        category=Category.RAM,
        name="8GB kit",
        specs={
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 4,
            "modules": 2,
            "form": "DIMM",
        },
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Small SSD",
        specs={"category": "storage", "interface": "nvme", "capacity_gb": 256, "form_factor": "m2_2280"},
    )
    insert_component(
        db_session,
        category=Category.PSU,
        name="Mid-range PSU",
        specs={
            "category": "psu",
            "wattage_w": 650,
            "form_factor": "ATX",
            "pcie_power_connectors": ["8-pin", "8-pin"],
        },
    )
    insert_component(
        db_session,
        category=Category.CASE,
        name="Generic ATX case",
        specs={
            "category": "case",
            "supported_form_factors": ["ATX"],
            "max_gpu_length_mm": 400,
            "max_cooler_height_mm": 170,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 2,
            "drive_bays_2_5": 2,
        },
    )
    insert_component(
        db_session,
        category=Category.COOLER,
        name="Generic air cooler",
        specs={
            "category": "cooler",
            "type": "air",
            "supported_sockets": ["AM4"],
            "height_mm": 150,
            "tdp_rating_w": 100,
        },
    )
    # Two GPUs: one barely over the inferred minimum, one wildly overkill.
    insert_component(
        db_session,
        category=Category.GPU,
        name="Modest 2GB GPU",
        specs={
            "category": "gpu",
            "vram_gb": 2,
            "tdp_w": 75,
            "length_mm": 200,
            "pcie_power_connectors": [],
            "vendor": "nvidia",
        },
    )
    insert_component(
        db_session,
        category=Category.GPU,
        name="Overkill 16GB GPU",
        specs={
            "category": "gpu",
            "vram_gb": 16,
            "tdp_w": 300,
            "length_mm": 300,
            "pcie_power_connectors": ["8-pin", "8-pin"],
            "vendor": "nvidia",
        },
    )

    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_crysis_minimal.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(
        prompt="I need a pc that can run crysis 1 at max resolution, but not more powerful than that.",
        max_builds=3,
        db=db_session,
        llm_client=client,
    )

    assert result.llm_used.interpret == "ok"
    assert result.llm_used.rank == "fallback"
    assert len(result.builds) >= 1
    first_build_gpus = {c.name for c in result.builds[0].components if c.category == Category.GPU}
    assert first_build_gpus == {"Modest 2GB GPU"}


def test_rank_builds_with_empty_pool_is_a_trivial_ok():
    from app.pipeline.recommend import rank_builds

    ranked, status = rank_builds([], ProjectRequirements(use_case="x"), FakeLLMClient([]))

    assert ranked == []
    assert status == "ok"


# --- release_year / era-based requests ---
# Regression tests for a real live-deployment bug: every recommendation kept
# using the same handful of recent components no matter the prompt, because
# prefilter_candidates handed the engine candidates in plain database order
# (effectively insertion order) and engine.generate_builds() only ever looks
# at the first `top_n` candidates per category -- an old/era-appropriate
# component seeded later than the first `top_n` rows could never be chosen,
# regardless of what was asked for (docs/ai-log.md has the full diagnosis).


def test_prefilter_applies_hard_released_no_later_than(db_session):
    insert_component(
        db_session, category=Category.CPU, name="Old CPU", specs={"category": "cpu"}, release_year=2008
    )
    insert_component(
        db_session, category=Category.CPU, name="New CPU", specs={"category": "cpu"}, release_year=2022
    )
    insert_component(db_session, category=Category.CPU, name="Unknown-year CPU", specs={"category": "cpu"})

    candidates = prefilter_candidates(
        db_session, ProjectRequirements(use_case="x", released_no_later_than=2010)
    )

    names = {c.name for c in candidates[Category.CPU]}
    assert names == {"Old CPU"}


def test_prefilter_applies_hard_released_no_earlier_than(db_session):
    insert_component(
        db_session, category=Category.GPU, name="Old GPU", specs={"category": "gpu"}, release_year=2012
    )
    insert_component(
        db_session, category=Category.GPU, name="New GPU", specs={"category": "gpu"}, release_year=2023
    )

    candidates = prefilter_candidates(
        db_session, ProjectRequirements(use_case="x", released_no_earlier_than=2020)
    )

    names = {c.name for c in candidates[Category.GPU]}
    assert names == {"New GPU"}


def test_prefilter_sorts_an_old_component_to_the_front_when_prefer_oldest(db_session):
    """The actual bug: engine.generate_builds() only looks at the first
    top_n (default 5) candidates per category. Six CPUs are inserted here --
    one more than top_n -- with the era-appropriate one inserted LAST (so it
    has the highest id and would never survive an id-ordered top_n cutoff).
    prefilter_candidates must still put it first when prefer_oldest is set,
    or it's permanently invisible to every recommendation regardless of
    what's asked for."""
    for i in range(5):
        insert_component(
            db_session,
            category=Category.CPU,
            name=f"Modern CPU {i}",
            specs={"category": "cpu"},
            release_year=2022,
        )
    insert_component(
        db_session, category=Category.CPU, name="Ancient CPU", specs={"category": "cpu"}, release_year=2005
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", prefer_oldest=True))

    assert candidates[Category.CPU][0].name == "Ancient CPU"


def test_prefilter_sorts_a_new_component_to_the_front_when_prefer_newest(db_session):
    for i in range(5):
        insert_component(
            db_session,
            category=Category.GPU,
            name=f"Old GPU {i}",
            specs={"category": "gpu"},
            release_year=2008,
        )
    insert_component(
        db_session, category=Category.GPU, name="Brand New GPU", specs={"category": "gpu"}, release_year=2024
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", prefer_newest=True))

    assert candidates[Category.GPU][0].name == "Brand New GPU"


def test_prefilter_leaves_candidate_order_unchanged_without_an_era_preference(db_session):
    """No prefer_oldest/prefer_newest and no min/released_no_later_than at all --
    era must never bias ordering by default, or every recommendation would
    silently skew toward one end of the inventory's age range even when
    nothing asked for that."""
    first = insert_component(
        db_session, category=Category.CPU, name="CPU A", specs={"category": "cpu"}, release_year=2005
    )
    second = insert_component(
        db_session, category=Category.CPU, name="CPU B", specs={"category": "cpu"}, release_year=2024
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x"))

    assert [c.id for c in candidates[Category.CPU]] == [first.id, second.id]


def test_deterministic_score_prefers_oldest_hardware_when_requested():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_release_year

    old_build = compatible_build(cpu=with_release_year(compatible_build().cpu, 2008))
    new_build = compatible_build(cpu=with_release_year(compatible_build().cpu, 2023))
    old_evaluation = BuildEvaluation(build=old_build, rule_results={})
    new_evaluation = BuildEvaluation(build=new_build, rule_results={})

    requirements = ProjectRequirements(use_case="x", prefer_oldest=True)
    assert deterministic_score(old_evaluation, requirements) > deterministic_score(
        new_evaluation, requirements
    )


def test_deterministic_score_prefers_newest_hardware_when_requested():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_release_year

    old_build = compatible_build(cpu=with_release_year(compatible_build().cpu, 2008))
    new_build = compatible_build(cpu=with_release_year(compatible_build().cpu, 2023))
    old_evaluation = BuildEvaluation(build=old_build, rule_results={})
    new_evaluation = BuildEvaluation(build=new_build, rule_results={})

    requirements = ProjectRequirements(use_case="x", prefer_newest=True)
    assert deterministic_score(new_evaluation, requirements) > deterministic_score(
        old_evaluation, requirements
    )


def test_era_request_end_to_end_picks_the_old_cpu_despite_being_seeded_last(db_session):
    """Full end-to-end reproduction of the reported bug: a user asks for
    hardware from 2010 or earlier, the inventory has far more than top_n
    modern CPUs seeded before the one matching CPU, and the pipeline must
    still return a build using it. released_no_later_than is a hard requirement
    on every category (not just CPU -- see _meets_hard_requirements), so
    every other component here needs a release_year within range too, or
    they'd be excluded themselves as "unknown era" the same as a
    too-modern part would be."""
    for i in range(8):
        insert_component(
            db_session,
            category=Category.CPU,
            name=f"Modern CPU {i}",
            specs={"category": "cpu", "socket": "AM4", "cores": 6, "tdp_w": 65, "memory_type": ["DDR4"]},
            release_year=2022,
        )
    insert_component(
        db_session,
        category=Category.CPU,
        name="Core 2 Duo E6600",
        specs={"category": "cpu", "socket": "LGA775", "cores": 2, "tdp_w": 65, "memory_type": ["DDR2"]},
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="ASUS P5B",
        specs={
            "category": "motherboard",
            "socket": "LGA775",
            "form_factor": "ATX",
            "memory_type": ["DDR2"],
            "memory_slots": 4,
            "max_memory_gb": 8,
            "sata_ports": 4,
        },
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.RAM,
        name="DDR2 2GB kit",
        specs={
            "category": "ram",
            "memory_type": "DDR2",
            "capacity_gb_per_module": 1,
            "modules": 2,
            "form": "DIMM",
        },
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Old HDD",
        specs={"category": "storage", "interface": "sata_hdd", "capacity_gb": 160, "form_factor": "3_5"},
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.PSU,
        name="Old PSU",
        specs={"category": "psu", "wattage_w": 450, "form_factor": "ATX", "pcie_power_connectors": []},
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.CASE,
        name="Old case",
        specs={"category": "case", "supported_form_factors": ["ATX"], "psu_form_factor": "ATX"},
        release_year=2006,
    )
    insert_component(
        db_session,
        category=Category.COOLER,
        name="Old stock cooler",
        specs={"category": "cooler", "type": "air", "supported_sockets": ["LGA775"], "height_mm": 55},
        release_year=2006,
    )

    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_released_no_later_than_2010.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(
        prompt="I need a build from hardware released in 2010 or earlier.",
        max_builds=3,
        db=db_session,
        llm_client=client,
    )

    assert len(result.builds) >= 1
    cpu_names = {c.name for c in result.builds[0].components if c.category == Category.CPU}
    assert cpu_names == {"Core 2 Duo E6600"}


# --- Deliberate diversification of the suggested builds ---
# Sorting candidates by relevance before the engine's top_n cutoff (the
# era-request fix above) means a single best CPU/motherboard/RAM
# combination can legitimately dominate the top of the ranking -- without
# an explicit diversity step, all of the suggested builds ended up being
# minor variations of that one combination (reported live: "the 3 build
# suggestions are still basically the same, but some pieces are changed
# out for each build").


def test_select_diverse_builds_avoids_repeating_a_cpu_when_alternatives_exist():
    import dataclasses

    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, cpu_ryzen_5_3600

    cpu_a = cpu_ryzen_5_3600()
    cpu_b = dataclasses.replace(cpu_a, id=101, name="Other CPU")
    # Three builds, but only two distinct CPUs -- the best-ranked two use
    # cpu_a, the third uses cpu_b. Ranked order (best first): 0, 1, 2.
    pool = [
        BuildEvaluation(build=compatible_build(cpu=cpu_a), rule_results={}),
        BuildEvaluation(build=compatible_build(cpu=cpu_a), rule_results={}),
        BuildEvaluation(build=compatible_build(cpu=cpu_b), rule_results={}),
    ]

    selected = _select_diverse_builds([0, 1, 2], pool, max_builds=2)

    chosen_cpu_ids = {pool[i].build.cpu.id for i in selected}
    assert chosen_cpu_ids == {cpu_a.id, cpu_b.id}
    assert selected[0] == 0  # the best-ranked build is still picked first


def test_select_diverse_builds_falls_back_to_repeats_when_not_enough_variety():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build

    # Only one distinct CPU/GPU combination available at all.
    pool = [
        BuildEvaluation(build=compatible_build(), rule_results={}),
        BuildEvaluation(build=compatible_build(), rule_results={}),
        BuildEvaluation(build=compatible_build(), rule_results={}),
    ]

    selected = _select_diverse_builds([0, 1, 2], pool, max_builds=3)

    # Still returns 3 builds -- never fewer just because nothing was diverse.
    assert selected == [0, 1, 2]


def test_select_diverse_builds_prefers_distinct_gpu_when_cpu_cant_vary():
    import dataclasses

    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, cpu_ryzen_5_3600, gpu_rtx_2060

    cpu_a = cpu_ryzen_5_3600()  # every build below uses this same CPU
    gpu_a = gpu_rtx_2060()
    gpu_b = dataclasses.replace(gpu_a, id=102, name="Other GPU")
    pool = [
        BuildEvaluation(build=compatible_build(cpu=cpu_a, gpu=gpu_a), rule_results={}),
        BuildEvaluation(build=compatible_build(cpu=cpu_a, gpu=gpu_b), rule_results={}),
        BuildEvaluation(build=compatible_build(cpu=cpu_a, gpu=gpu_a), rule_results={}),
    ]

    selected = _select_diverse_builds([0, 1, 2], pool, max_builds=2)

    chosen_gpu_ids = {pool[i].build.gpu.id for i in selected}
    assert selected[0] == 0
    assert chosen_gpu_ids == {gpu_a.id, gpu_b.id}


def test_recommend_diversifies_cpu_across_the_returned_builds(db_session):
    """End-to-end: three compatible CPUs are available, all tied on
    deterministic score (same specs), ranking is forced to fall back --
    the three returned builds must use three different CPUs, not the same
    one three times over with only storage/cooler swapped."""
    for i in range(3):
        insert_component(
            db_session,
            category=Category.CPU,
            name=f"CPU option {i}",
            specs={
                "category": "cpu",
                "socket": "AM4",
                "cores": 6,
                "tdp_w": 65,
                "integrated_graphics": False,
                "memory_type": ["DDR4"],
            },
        )
    seed_compatible_inventory(db_session)  # motherboard/ram/gpu/storage/psu/case/cooler, AM4

    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_generic.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="a gaming pc", max_builds=3, db=db_session, llm_client=client)

    assert len(result.builds) == 3
    cpu_names = {c.name for build in result.builds for c in build.components if c.category == Category.CPU}
    assert len(cpu_names) == 3


# --- Cross-category relevance sort (socket/memory-type aware) ---
# Regression tests for a real live bug: sorting CPU candidates purely by
# how closely they match a stated min_cpu_cores, independently of which
# sockets the top motherboard candidates actually have, let many
# same-overshoot CPUs from incompatible sockets crowd out the one CPU that
# would have actually paired with something. Confirmed against the real
# seed data: ten historical CPUs tied at "exactly meets min_cpu_cores=4"
# spanned six different sockets, none of which matched any of the top-5
# independently-ranked motherboards -- "no compatible builds" despite a
# proven-compatible combination (AMD Ryzen 5 3600 + its own motherboard)
# existing elsewhere in the same inventory.


def test_prefilter_promotes_a_socket_compatible_cpu_over_many_tied_incompatible_ones(db_session):
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="AM4 board",
        specs={"category": "motherboard", "socket": "AM4", "form_factor": "ATX", "memory_type": ["DDR4"]},
    )
    # Five CPUs that exactly meet min_cpu_cores=4 (overshoot 0), none AM4.
    for socket in ["LGA775", "AM2+", "LGA1366", "AM3", "FM2+"]:
        insert_component(
            db_session,
            category=Category.CPU,
            name=f"Old {socket} CPU",
            specs={"category": "cpu", "socket": socket, "cores": 4},
        )
    # One CPU that overshoots (6 cores) but actually matches the board.
    insert_component(
        db_session,
        category=Category.CPU,
        name="AM4 CPU",
        specs={"category": "cpu", "socket": "AM4", "cores": 6, "memory_type": ["DDR4"]},
    )

    candidates = prefilter_candidates(
        db_session, ProjectRequirements(use_case="x", min_cpu_cores=4), top_n_hint=5
    )

    top_cpu_names = [c.name for c in candidates[Category.CPU][:5]]
    assert "AM4 CPU" in top_cpu_names


def test_prefilter_promotes_ram_matching_motherboard_and_cpu_memory_type(db_session):
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="DDR4 board",
        specs={"category": "motherboard", "socket": "AM4", "form_factor": "ATX", "memory_type": ["DDR4"]},
    )
    insert_component(
        db_session,
        category=Category.CPU,
        name="DDR4 CPU",
        specs={"category": "cpu", "socket": "AM4", "cores": 6, "memory_type": ["DDR4"]},
    )
    # Several lower-id, non-matching-type RAM kits, plus one DDR4 kit with
    # a higher id (so it would lose a plain id tiebreak).
    for mem_type in ["DDR2", "DDR3", "DDR", "DDR2"]:
        insert_component(
            db_session,
            category=Category.RAM,
            name=f"{mem_type} kit",
            specs={"category": "ram", "memory_type": mem_type},
        )
    insert_component(
        db_session, category=Category.RAM, name="DDR4 kit", specs={"category": "ram", "memory_type": "DDR4"}
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x"), top_n_hint=5)

    top_ram_names = [c.name for c in candidates[Category.RAM][:5]]
    assert "DDR4 kit" in top_ram_names


def test_recommend_finds_a_build_despite_many_overshoot_tied_incompatible_cpus(db_session):
    """End-to-end reproduction of the live bug, using the exact shape that
    triggered it: a stated min_cpu_cores with far more than top_n
    exactly-matching but socket-incompatible CPUs ahead of the one CPU
    that actually pairs with the available motherboard/RAM/GPU."""
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="AM4 board",
        specs={
            "category": "motherboard",
            "socket": "AM4",
            "form_factor": "ATX",
            "memory_type": ["DDR4"],
            "memory_slots": 4,
            "max_memory_gb": 64,
            "sata_ports": 4,
        },
    )
    for socket in ["LGA775", "AM2+", "LGA1366", "AM3", "FM2+", "LGA1151"]:
        insert_component(
            db_session,
            category=Category.CPU,
            name=f"Old {socket} CPU",
            specs={"category": "cpu", "socket": socket, "cores": 4, "tdp_w": 65},
        )
    insert_component(
        db_session,
        category=Category.CPU,
        name="AMD Ryzen 5 3600",
        specs={
            "category": "cpu",
            "socket": "AM4",
            "cores": 6,
            "tdp_w": 65,
            "integrated_graphics": False,
            "memory_type": ["DDR4"],
        },
    )
    insert_component(
        db_session,
        category=Category.RAM,
        name="DDR4 16GB",
        specs={
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "form": "DIMM",
        },
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="NVMe 1TB",
        specs={"category": "storage", "interface": "nvme", "capacity_gb": 1000, "form_factor": "m2_2280"},
    )
    insert_component(
        db_session,
        category=Category.PSU,
        name="650W PSU",
        specs={"category": "psu", "wattage_w": 650, "form_factor": "ATX", "pcie_power_connectors": []},
    )
    insert_component(
        db_session,
        category=Category.CASE,
        name="ATX case",
        specs={"category": "case", "supported_form_factors": ["ATX"], "psu_form_factor": "ATX"},
    )
    insert_component(
        db_session,
        category=Category.COOLER,
        name="AM4 cooler",
        specs={"category": "cooler", "type": "air", "supported_sockets": ["AM4"], "height_mm": 150},
    )

    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_min_cpu_cores_4.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="a pc with at least 4 cores", max_builds=3, db=db_session, llm_client=client)

    assert len(result.builds) >= 1
    cpu_names = {c.name for build in result.builds for c in build.components if c.category == Category.CPU}
    assert "AMD Ryzen 5 3600" in cpu_names


# --- prefer_max_vram ---
# Regression tests for a real live bug: "run the biggest model available
# from my inventory" produced 3 near-identical builds with NO gpu at all,
# because deterministic_score's gentle, always-on power-draw nudge always
# favors a GPU-less build over an otherwise-identical one with a GPU, and
# nothing offset that unless a concrete min_vram_gb happened to be set --
# which an inherently relative request like "the biggest GPU I have" can
# never produce, since the LLM doesn't know what's in the inventory.


def test_deterministic_score_prefers_a_gpu_over_none_when_prefer_max_vram():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build

    with_gpu = BuildEvaluation(build=compatible_build(), rule_results={})
    without_gpu = BuildEvaluation(build=compatible_build(gpu=None), rule_results={})

    requirements = ProjectRequirements(use_case="x", prefer_max_vram=True)
    assert deterministic_score(with_gpu, requirements) > deterministic_score(without_gpu, requirements)


def test_deterministic_score_prefers_more_vram_when_prefer_max_vram():
    from app.compatibility.types import BuildEvaluation
    from tests.fixtures.sample_inventory import compatible_build, with_specs

    small_gpu = BuildEvaluation(
        build=compatible_build(gpu=with_specs(compatible_build().gpu, vram_gb=6)), rule_results={}
    )
    big_gpu = BuildEvaluation(
        build=compatible_build(gpu=with_specs(compatible_build().gpu, vram_gb=24)), rule_results={}
    )

    requirements = ProjectRequirements(use_case="x", prefer_max_vram=True)
    assert deterministic_score(big_gpu, requirements) > deterministic_score(small_gpu, requirements)


def test_prefilter_sorts_gpu_by_descending_vram_when_prefer_max_vram(db_session):
    insert_component(
        db_session, category=Category.GPU, name="Small GPU", specs={"category": "gpu", "vram_gb": 4}
    )
    insert_component(
        db_session, category=Category.GPU, name="Huge GPU", specs={"category": "gpu", "vram_gb": 24}
    )
    insert_component(
        db_session, category=Category.GPU, name="Medium GPU", specs={"category": "gpu", "vram_gb": 10}
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", prefer_max_vram=True))

    assert [c.name for c in candidates[Category.GPU]] == ["Huge GPU", "Medium GPU", "Small GPU"]


def test_recommend_includes_a_gpu_when_the_user_wants_the_biggest_model(db_session):
    seed_compatible_inventory(db_session)  # includes a 6GB GPU
    insert_component(
        db_session,
        category=Category.GPU,
        name="Bigger GPU",
        specs={
            "category": "gpu",
            "vram_gb": 16,
            "tdp_w": 300,
            "length_mm": 300,
            "pcie_power_connectors": ["8-pin", "8-pin"],
            "vendor": "nvidia",
        },
    )
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_prefer_max_vram.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(
        prompt="run the biggest model available from my inventory",
        max_builds=3,
        db=db_session,
        llm_client=client,
    )

    assert len(result.builds) >= 1
    gpu_names = {c.name for c in result.builds[0].components if c.category == Category.GPU}
    assert gpu_names == {"Bigger GPU"}


# --- Storage capacity scoring/sorting ---
# Regression tests for a real live bug: "I still only get recommended one
# storage disk per build" despite multi-drive support existing in the
# engine (engine.py's MAX_STORAGE_DRIVES) -- deterministic_score had no
# opinion on storage at all, so a 1-drive and an otherwise-identical
# 2-drive build tied exactly, and _storage_combos always lists every
# 1-drive option before any 2-drive one, so the tie's stable sort
# permanently buried every multi-drive build once the ranking pool was
# truncated. Separately, the storage candidates 2-drive combos are built
# from (MAX_STORAGE_PAIR_CANDIDATES) were sorted by plain id, not
# capacity, so even a surfaced 2-drive combo could lose on total capacity
# to a single large drive that was never a bug, just an unhelpful default.


def test_deterministic_score_prefers_more_total_storage_capacity():
    from app.compatibility.types import BuildEvaluation, CandidateComponent
    from app.schemas.components import StorageSpecs
    from tests.fixtures.sample_inventory import compatible_build, storage_nvme_1tb

    second_drive = CandidateComponent(
        id=999, name="Second drive", specs=StorageSpecs(capacity_gb=4000, interface="sata_hdd")
    )
    one_drive = BuildEvaluation(build=compatible_build(), rule_results={})
    two_drives = BuildEvaluation(
        build=compatible_build(storage=[storage_nvme_1tb(), second_drive]), rule_results={}
    )

    requirements = ProjectRequirements(use_case="x")
    assert deterministic_score(two_drives, requirements) > deterministic_score(one_drive, requirements)


def test_prefilter_sorts_storage_by_descending_capacity_without_a_stated_minimum(db_session):
    insert_component(
        db_session, category=Category.STORAGE, name="Small", specs={"category": "storage", "capacity_gb": 500}
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Huge",
        specs={"category": "storage", "capacity_gb": 16000},
    )
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Medium",
        specs={"category": "storage", "capacity_gb": 2000},
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x"))

    assert [c.name for c in candidates[Category.STORAGE]] == ["Huge", "Medium", "Small"]


def test_recommend_includes_a_two_drive_build_when_sensible(db_session):
    seed_compatible_inventory(db_session)  # includes a 1TB NVMe
    insert_component(
        db_session,
        category=Category.STORAGE,
        name="Big second drive",
        specs={"category": "storage", "interface": "sata_hdd", "capacity_gb": 8000, "form_factor": "3_5"},
    )
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_generic.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="a pc with lots of storage", max_builds=3, db=db_session, llm_client=client)

    assert any(
        len([c for c in build.components if c.category == Category.STORAGE]) == 2 for build in result.builds
    )


# --- required_categories is an actual hard requirement ---
# Found by code review: the LLM fills in `required_categories`, but the
# pipeline only ever forced a discrete GPU when `min_vram_gb` happened to be
# set. A user who asks for a graphics card without naming a VRAM number got
# `required_categories=["gpu"]` -- which was parsed, stored, and then
# silently ignored, so a GPU-less build could still be recommended (and in
# fact scored *higher*, because deterministic_score's always-on power-draw
# nudge penalises the GPU's TDP with nothing opposing it).


def _seed_igpu_inventory(db, *, with_gpu: bool) -> None:
    """A build-able inventory whose CPU has integrated graphics, so a
    GPU-less build satisfies display_output_available on its own and the
    engine genuinely offers both options."""
    insert_component(
        db,
        category=Category.CPU,
        name="Ryzen 5 5600G",
        specs={
            "category": "cpu",
            "socket": "AM4",
            "cores": 6,
            "tdp_w": 65,
            "integrated_graphics": True,
            "memory_type": ["DDR4"],
        },
    )
    insert_component(
        db,
        category=Category.MOTHERBOARD,
        name="AM4 board",
        specs={
            "category": "motherboard",
            "socket": "AM4",
            "form_factor": "ATX",
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
        name="16GB DDR4",
        specs={
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "form": "DIMM",
        },
    )
    insert_component(
        db,
        category=Category.STORAGE,
        name="1TB NVMe",
        specs={"category": "storage", "interface": "nvme", "capacity_gb": 1000, "form_factor": "m2_2280"},
    )
    insert_component(
        db,
        category=Category.PSU,
        name="650W PSU",
        specs={
            "category": "psu",
            "wattage_w": 650,
            "form_factor": "ATX",
            "pcie_power_connectors": ["8-pin", "8-pin"],
        },
    )
    insert_component(
        db,
        category=Category.CASE,
        name="ATX case",
        specs={
            "category": "case",
            "supported_form_factors": ["ATX", "mATX"],
            "max_gpu_length_mm": 400,
            "max_cooler_height_mm": 170,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 2,
            "drive_bays_2_5": 2,
        },
    )
    insert_component(
        db,
        category=Category.COOLER,
        name="AM4 cooler",
        specs={
            "category": "cooler",
            "type": "air",
            "supported_sockets": ["AM4"],
            "height_mm": 60,
            "tdp_rating_w": 95,
        },
    )
    if with_gpu:
        insert_component(
            db,
            category=Category.GPU,
            name="RTX 2060",
            specs={
                "category": "gpu",
                "vram_gb": 6,
                "tdp_w": 160,
                "length_mm": 229,
                "pcie_power_connectors": ["8-pin"],
                "vendor": "nvidia",
            },
        )


def test_required_categories_gpu_forces_every_build_to_include_a_gpu(db_session):
    _seed_igpu_inventory(db_session, with_gpu=True)
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_requires_gpu.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="I need a graphics card in it", max_builds=3, db=db_session, llm_client=client)

    assert result.builds, "the inventory can build with a GPU, so something must come back"
    for build in result.builds:
        categories = [c.category for c in build.components]
        assert Category.GPU in categories, "required_categories asked for a GPU but a build omitted it"


def test_required_categories_reports_a_missing_category_when_none_is_available(db_session):
    _seed_igpu_inventory(db_session, with_gpu=False)
    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_requires_gpu.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="I need a graphics card in it", max_builds=3, db=db_session, llm_client=client)

    assert Category.GPU in result.missing
    assert result.builds == []


# --- The ranking pool itself has to be diverse ---
# The diversity step (_select_diverse_builds) ran on the *pool*, and the pool
# was simply the top-N builds by deterministic score. So whenever a single
# CPU scored best, it filled the whole pool and the diversity step had no
# variety left to choose from -- it fell back to repeats, which is exactly
# what was reported live: "the 3 build suggestions are still basically the
# same, but some pieces are changed out for each build". The earlier
# diversity test only passed because its tiny inventory produced fewer
# builds than the pool could hold, so all the variety survived truncation.


def test_recommend_diversifies_cpu_even_when_one_cpu_dominates_the_score(db_session):
    # Three AM4 CPUs with clearly different TDPs, so they do *not* tie: the
    # 65W one scores strictly best, and every build using it outranks every
    # build using the others.
    for name, tdp in [("Efficient CPU", 65), ("Thirsty CPU", 200), ("Furnace CPU", 250)]:
        insert_component(
            db_session,
            category=Category.CPU,
            name=name,
            specs={
                "category": "cpu",
                "socket": "AM4",
                "cores": 6,
                "tdp_w": tdp,
                "integrated_graphics": True,
                "memory_type": ["DDR4"],
            },
        )
    insert_component(
        db_session,
        category=Category.MOTHERBOARD,
        name="AM4 board",
        specs={
            "category": "motherboard",
            "socket": "AM4",
            "form_factor": "ATX",
            "memory_type": ["DDR4"],
            "memory_slots": 4,
            "max_memory_gb": 64,
            "m2_slots": 0,
            "sata_ports": 4,
            "pcie_x16_slots": 1,
        },
    )
    insert_component(
        db_session,
        category=Category.RAM,
        name="16GB DDR4",
        specs={
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "form": "DIMM",
        },
    )
    # Three identical-capacity SATA drives -> 3 single-drive options plus 3
    # two-drive pairs = 6 storage combinations per CPU. Identical capacity
    # keeps the storage-capacity nudge from reordering CPUs by accident.
    for i in range(3):
        insert_component(
            db_session,
            category=Category.STORAGE,
            name=f"500GB SATA {i}",
            specs={
                "category": "storage",
                "interface": "sata_ssd",
                "capacity_gb": 500,
                "form_factor": "2_5",
            },
        )
    for i in range(2):
        insert_component(
            db_session,
            category=Category.PSU,
            name=f"PSU {i}",
            specs={
                "category": "psu",
                "wattage_w": 750,
                "form_factor": "ATX",
                "pcie_power_connectors": ["8-pin", "8-pin"],
            },
        )
    for i in range(2):
        insert_component(
            db_session,
            category=Category.COOLER,
            name=f"Cooler {i}",
            specs={
                "category": "cooler",
                "type": "air",
                "supported_sockets": ["AM4"],
                "height_mm": 60,
                "tdp_rating_w": 250,
            },
        )
    insert_component(
        db_session,
        category=Category.CASE,
        name="ATX case",
        specs={
            "category": "case",
            "supported_form_factors": ["ATX"],
            "max_gpu_length_mm": 400,
            "max_cooler_height_mm": 170,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 4,
            "drive_bays_2_5": 4,
        },
    )

    client = FakeLLMClient(
        [
            load_fixture("valid_requirements_generic.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("hallucinated_ranking.json"),
            load_fixture("valid_chat_reply.json"),
        ]
    )

    result = recommend(prompt="a general office pc", max_builds=3, db=db_session, llm_client=client)

    assert len(result.builds) == 3
    cpu_names = {c.name for build in result.builds for c in build.components if c.category == Category.CPU}
    assert len(cpu_names) == 3, f"all three builds should use a different CPU, got {cpu_names}"


# --- The era bound is the one direction this model reliably inverts ---
# Measured against qwen2.5:7b-instruct over eight phrasings: the original
# max_release_year/min_release_year pair scored 3/6, reading "from 2010 or
# earlier" as min_release_year=2010 -- admitting newer hardware and excluding
# the genuinely old parts asked for. Renaming the fields so they state their
# own direction, plus two worked examples in the prompt, took it to 6/8. The
# validator below is the deterministic backstop for the rest: an inverted era
# bound produces a confident answer built from the opposite of the request,
# which is worse than no answer.


def test_prefer_oldest_with_a_lower_year_bound_is_rejected_and_retried():
    import pytest

    from app.pipeline.recommend import _validate_requirements

    contradictory = ProjectRequirements(
        use_case="hardware from 2010 or earlier, the oldest I have",
        prefer_oldest=True,
        released_no_earlier_than=2010,  # the inversion: excludes everything old
    )
    with pytest.raises(ValueError, match="released_no_earlier_than"):
        _validate_requirements(contradictory)


def test_prefer_newest_with_an_upper_year_bound_is_rejected():
    import pytest

    from app.pipeline.recommend import _validate_requirements

    with pytest.raises(ValueError, match="released_no_later_than"):
        _validate_requirements(
            ProjectRequirements(use_case="my newest parts", prefer_newest=True, released_no_later_than=2015)
        )


def test_coherent_era_requirements_are_left_alone():
    """The combinations that are *not* contradictory must pass untouched --
    including "the oldest I have, but nothing before 2010", which produces
    prefer_oldest plus an upper bound and is a perfectly sensible request."""
    from app.pipeline.recommend import _validate_requirements

    for requirements in [
        ProjectRequirements(use_case="x", prefer_oldest=True, released_no_later_than=2010),
        ProjectRequirements(use_case="x", prefer_newest=True, released_no_earlier_than=2020),
        ProjectRequirements(use_case="x", released_no_later_than=2010, released_no_earlier_than=2005),
        ProjectRequirements(use_case="x", prefer_oldest=True),
        ProjectRequirements(use_case="x"),
    ]:
        _validate_requirements(requirements)  # must not raise


def test_an_inverted_era_bound_falls_back_rather_than_reversing_the_request(db_session):
    """End-to-end: a model that insists on the inverted bound must not have
    it silently applied. Losing the era constraint is recoverable -- the user
    can rephrase; building from the opposite of what they asked is not."""
    seed_compatible_inventory(db_session)
    inverted = (
        '{"use_case": "hardware from 2010 or earlier", "prefer_oldest": true, '
        '"released_no_earlier_than": 2010, "headless": false, "required_categories": [], '
        '"notes": ""}'
    )
    client = FakeLLMClient(
        [inverted, inverted, load_fixture("valid_ranking.json"), load_fixture("valid_chat_reply.json")]
    )

    result = recommend(prompt="hardware from 2010 or earlier", max_builds=3, db=db_session, llm_client=client)

    assert result.llm_used.interpret == "fallback"
