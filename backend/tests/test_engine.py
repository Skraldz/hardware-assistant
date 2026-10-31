from app.compatibility.engine import generate_builds
from app.enums import Category
from tests.fixtures.sample_inventory import (
    case_atx,
    cooler_wraith_stealth,
    cpu_ryzen_5_3600,
    gpu_rtx_2060,
    motherboard_b450m,
    psu_650w,
    ram_corsair_16gb,
    storage_nvme_1tb,
    with_specs,
)


def base_candidates() -> dict[Category, list]:
    return {
        Category.CPU: [cpu_ryzen_5_3600()],
        Category.MOTHERBOARD: [motherboard_b450m()],
        Category.RAM: [ram_corsair_16gb()],
        Category.GPU: [gpu_rtx_2060()],
        Category.STORAGE: [storage_nvme_1tb()],
        Category.PSU: [psu_650w()],
        Category.CASE: [case_atx()],
        Category.COOLER: [cooler_wraith_stealth()],
    }


def test_compatible_inventory_produces_one_valid_build():
    result = generate_builds(base_candidates())
    assert result.missing == []
    assert len(result.builds) == 1
    assert result.builds[0].build.gpu is not None


def test_incompatible_socket_produces_no_builds():
    candidates = base_candidates()
    candidates[Category.MOTHERBOARD] = [with_specs(motherboard_b450m(), socket="LGA1700")]

    result = generate_builds(candidates)
    assert result.builds == []
    assert result.missing == []


def test_missing_required_category_is_reported():
    candidates = base_candidates()
    del candidates[Category.PSU]

    result = generate_builds(candidates)
    assert result.missing == [Category.PSU]
    assert result.builds == []


def test_headless_allows_build_without_gpu():
    candidates = base_candidates()
    del candidates[Category.GPU]
    candidates[Category.CPU] = [with_specs(cpu_ryzen_5_3600(), integrated_graphics=True)]

    result = generate_builds(candidates, headless=True)
    assert len(result.builds) == 1
    assert result.builds[0].build.gpu is None


def test_integrated_graphics_allows_build_without_gpu_even_when_not_headless():
    candidates = base_candidates()
    del candidates[Category.GPU]
    candidates[Category.CPU] = [with_specs(cpu_ryzen_5_3600(), integrated_graphics=True)]

    result = generate_builds(candidates, headless=False)
    assert len(result.builds) == 1


def test_no_gpu_and_no_integrated_graphics_yields_no_builds_when_not_headless():
    candidates = base_candidates()
    del candidates[Category.GPU]
    candidates[Category.CPU] = [with_specs(cpu_ryzen_5_3600(), integrated_graphics=False)]

    result = generate_builds(candidates, headless=False)
    assert result.builds == []
    assert result.missing == []


def test_unknown_rule_result_is_surfaced_as_a_warning_not_a_rejection():
    candidates = base_candidates()
    candidates[Category.COOLER] = [with_specs(cooler_wraith_stealth(), tdp_rating_w=None)]

    result = generate_builds(candidates)
    assert len(result.builds) == 1
    assert len(result.builds[0].warnings) >= 1


def test_single_drive_only_combos_when_motherboard_has_one_m2_slot():
    candidates = base_candidates()
    candidates[Category.STORAGE] = [storage_nvme_1tb(), storage_nvme_1tb()]
    # motherboard_b450m() has m2_slots=1 -- a 2-drive NVMe combo can't fit,
    # so only single-drive builds should survive the compatibility rules.
    result = generate_builds(candidates)
    assert len(result.builds) >= 1
    assert all(len(b.build.storage) == 1 for b in result.builds)


def test_two_drive_build_appears_when_motherboard_has_enough_m2_slots():
    candidates = base_candidates()
    candidates[Category.STORAGE] = [storage_nvme_1tb(), storage_nvme_1tb()]
    candidates[Category.MOTHERBOARD] = [with_specs(motherboard_b450m(), m2_slots=2)]

    result = generate_builds(candidates)

    two_drive_builds = [b for b in result.builds if len(b.build.storage) == 2]
    assert len(two_drive_builds) >= 1


def test_top_n_limits_how_many_candidates_per_category_are_considered():
    candidates = base_candidates()
    candidates[Category.CPU] = [
        with_specs(cpu_ryzen_5_3600(), socket="LGA1700"),  # incompatible, listed first
        cpu_ryzen_5_3600(),  # compatible, listed second
    ]

    assert generate_builds(candidates, top_n=1).builds == []
    assert len(generate_builds(candidates, top_n=2).builds) == 1
