from app.enums import Category, Condition, SpecsSource
from app.models import Component
from app.pipeline.recommend import deterministic_score, prefilter_candidates, recommend
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


def test_prefilter_applies_hard_max_release_year(db_session):
    insert_component(
        db_session, category=Category.CPU, name="Old CPU", specs={"category": "cpu"}, release_year=2008
    )
    insert_component(
        db_session, category=Category.CPU, name="New CPU", specs={"category": "cpu"}, release_year=2022
    )
    insert_component(db_session, category=Category.CPU, name="Unknown-year CPU", specs={"category": "cpu"})

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", max_release_year=2010))

    names = {c.name for c in candidates[Category.CPU]}
    assert names == {"Old CPU"}


def test_prefilter_applies_hard_min_release_year(db_session):
    insert_component(
        db_session, category=Category.GPU, name="Old GPU", specs={"category": "gpu"}, release_year=2012
    )
    insert_component(
        db_session, category=Category.GPU, name="New GPU", specs={"category": "gpu"}, release_year=2023
    )

    candidates = prefilter_candidates(db_session, ProjectRequirements(use_case="x", min_release_year=2020))

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
    """No prefer_oldest/prefer_newest and no min/max_release_year at all --
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
    still return a build using it. max_release_year is a hard requirement
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
            load_fixture("valid_requirements_max_release_year_2010.json"),
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
