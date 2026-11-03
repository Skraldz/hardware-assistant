"""Every rule in SPEC.md §6, tested for pass, fail, and unknown (missing
data). Rules with a "not applicable" shortcut (gpu_fits_case,
cooler_fits_case, psu_has_gpu_connectors, display_output_available) get an
extra case for that.
"""

from app.compatibility import rules
from tests.fixtures.sample_inventory import compatible_build, storage_nvme_1tb, with_specs

# --- cpu_socket_matches_board ---


def test_cpu_socket_matches_board_pass():
    build = compatible_build()
    assert rules.cpu_socket_matches_board(build).status == "pass"


def test_cpu_socket_matches_board_fail():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, socket="LGA1700"))
    assert rules.cpu_socket_matches_board(build).status == "fail"


def test_cpu_socket_matches_board_unknown():
    build = compatible_build(cpu=with_specs(compatible_build().cpu, socket=None))
    assert rules.cpu_socket_matches_board(build).status == "unknown"


# --- ram_type_matches ---


def test_ram_type_matches_pass():
    build = compatible_build()
    assert rules.ram_type_matches(build).status == "pass"


def test_ram_type_matches_fail():
    build = compatible_build(ram=with_specs(compatible_build().ram, memory_type="DDR5"))
    assert rules.ram_type_matches(build).status == "fail"


def test_ram_type_matches_unknown():
    build = compatible_build(ram=with_specs(compatible_build().ram, memory_type=None))
    assert rules.ram_type_matches(build).status == "unknown"


# --- ram_form_is_dimm ---


def test_ram_form_is_dimm_pass():
    build = compatible_build()
    assert rules.ram_form_is_dimm(build).status == "pass"


def test_ram_form_is_dimm_fail():
    build = compatible_build(ram=with_specs(compatible_build().ram, form="SODIMM"))
    assert rules.ram_form_is_dimm(build).status == "fail"


def test_ram_form_is_dimm_unknown():
    build = compatible_build(ram=with_specs(compatible_build().ram, form=None))
    assert rules.ram_form_is_dimm(build).status == "unknown"


# --- ram_slots_sufficient ---


def test_ram_slots_sufficient_pass():
    build = compatible_build()
    assert rules.ram_slots_sufficient(build).status == "pass"


def test_ram_slots_sufficient_fail():
    build = compatible_build(ram=with_specs(compatible_build().ram, modules=5))
    assert rules.ram_slots_sufficient(build).status == "fail"


def test_ram_slots_sufficient_unknown():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, memory_slots=None))
    assert rules.ram_slots_sufficient(build).status == "unknown"


# --- ram_capacity_within_board_max ---


def test_ram_capacity_within_board_max_pass():
    build = compatible_build()
    assert rules.ram_capacity_within_board_max(build).status == "pass"


def test_ram_capacity_within_board_max_fail():
    build = compatible_build(ram=with_specs(compatible_build().ram, capacity_gb_per_module=64))
    assert rules.ram_capacity_within_board_max(build).status == "fail"


def test_ram_capacity_within_board_max_unknown():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, max_memory_gb=None))
    assert rules.ram_capacity_within_board_max(build).status == "unknown"


# --- board_fits_case ---


def test_board_fits_case_pass():
    build = compatible_build()
    assert rules.board_fits_case(build).status == "pass"


def test_board_fits_case_fail():
    build = compatible_build(case=with_specs(compatible_build().case, supported_form_factors=["ITX"]))
    assert rules.board_fits_case(build).status == "fail"


def test_board_fits_case_unknown():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, form_factor=None))
    assert rules.board_fits_case(build).status == "unknown"


# --- gpu_fits_case ---


def test_gpu_fits_case_pass():
    build = compatible_build()
    assert rules.gpu_fits_case(build).status == "pass"


def test_gpu_fits_case_fail():
    build = compatible_build(gpu=with_specs(compatible_build().gpu, length_mm=500))
    assert rules.gpu_fits_case(build).status == "fail"


def test_gpu_fits_case_unknown():
    build = compatible_build(case=with_specs(compatible_build().case, max_gpu_length_mm=None))
    assert rules.gpu_fits_case(build).status == "unknown"


def test_gpu_fits_case_not_applicable_without_gpu():
    build = compatible_build(gpu=None)
    assert rules.gpu_fits_case(build).status == "pass"


# --- gpu_has_pcie_slot (issue #5) ---
# The slot count was modelled and populated from the start, but no rule read
# it, so a discrete GPU on a board with zero x16 slots passed all checks.


def test_gpu_has_pcie_slot_pass():
    build = compatible_build()
    assert rules.gpu_has_pcie_slot(build).status == "pass"


def test_gpu_has_pcie_slot_fail():
    board = with_specs(compatible_build().motherboard, pcie_x16_slots=0)
    assert rules.gpu_has_pcie_slot(compatible_build(motherboard=board)).status == "fail"


def test_gpu_has_pcie_slot_unknown():
    board = with_specs(compatible_build().motherboard, pcie_x16_slots=None)
    assert rules.gpu_has_pcie_slot(compatible_build(motherboard=board)).status == "unknown"


def test_gpu_has_pcie_slot_not_applicable_without_gpu():
    """A slotless board is perfectly fine for an iGPU-only build, so this
    rule must not reject it -- the same "not applicable" branch the other
    four conditional rules have."""
    board = with_specs(compatible_build().motherboard, pcie_x16_slots=0)
    assert rules.gpu_has_pcie_slot(compatible_build(motherboard=board, gpu=None)).status == "pass"


def test_engine_rejects_a_gpu_build_on_a_slotless_board():
    """End-to-end through the engine: the rule has to be registered in
    ALL_RULES, not merely defined."""
    from app.compatibility.engine import evaluate_build, is_build_valid

    board = with_specs(compatible_build().motherboard, pcie_x16_slots=0)
    results = evaluate_build(compatible_build(motherboard=board))
    assert results["gpu_has_pcie_slot"].status == "fail"
    assert not is_build_valid(results)


# --- cooler_fits_case ---


def test_cooler_fits_case_pass():
    build = compatible_build()
    assert rules.cooler_fits_case(build).status == "pass"


def test_cooler_fits_case_fail():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, height_mm=200))
    assert rules.cooler_fits_case(build).status == "fail"


def test_cooler_fits_case_unknown():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, height_mm=None))
    assert rules.cooler_fits_case(build).status == "unknown"


def test_cooler_fits_case_unknown_when_type_missing():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, type=None))
    assert rules.cooler_fits_case(build).status == "unknown"


def test_cooler_fits_case_not_applicable_for_aio():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, type="aio", height_mm=None))
    assert rules.cooler_fits_case(build).status == "pass"


# --- cooler_supports_socket ---


def test_cooler_supports_socket_pass():
    build = compatible_build()
    assert rules.cooler_supports_socket(build).status == "pass"


def test_cooler_supports_socket_fail():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, supported_sockets=["LGA1700"]))
    assert rules.cooler_supports_socket(build).status == "fail"


def test_cooler_supports_socket_unknown():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, supported_sockets=None))
    assert rules.cooler_supports_socket(build).status == "unknown"


# --- cooler_handles_tdp ---


def test_cooler_handles_tdp_pass():
    build = compatible_build()
    assert rules.cooler_handles_tdp(build).status == "pass"


def test_cooler_handles_tdp_fail():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, tdp_rating_w=30))
    assert rules.cooler_handles_tdp(build).status == "fail"


def test_cooler_handles_tdp_unknown():
    build = compatible_build(cooler=with_specs(compatible_build().cooler, tdp_rating_w=None))
    assert rules.cooler_handles_tdp(build).status == "unknown"


# --- psu_wattage_sufficient ---


def test_psu_wattage_sufficient_pass():
    build = compatible_build()
    assert rules.psu_wattage_sufficient(build).status == "pass"


def test_psu_wattage_sufficient_fail():
    build = compatible_build(psu=with_specs(compatible_build().psu, wattage_w=100))
    assert rules.psu_wattage_sufficient(build).status == "fail"


def test_psu_wattage_sufficient_unknown():
    build = compatible_build(cpu=with_specs(compatible_build().cpu, tdp_w=None))
    assert rules.psu_wattage_sufficient(build).status == "unknown"


def test_psu_wattage_sufficient_unknown_when_gpu_tdp_missing():
    build = compatible_build(gpu=with_specs(compatible_build().gpu, tdp_w=None))
    assert rules.psu_wattage_sufficient(build).status == "unknown"


# --- psu_has_gpu_connectors ---


def test_psu_has_gpu_connectors_pass():
    build = compatible_build()
    assert rules.psu_has_gpu_connectors(build).status == "pass"


def test_psu_has_gpu_connectors_fail():
    build = compatible_build(gpu=with_specs(compatible_build().gpu, pcie_power_connectors=["16-pin"]))
    assert rules.psu_has_gpu_connectors(build).status == "fail"


def test_psu_has_gpu_connectors_unknown():
    build = compatible_build(gpu=with_specs(compatible_build().gpu, pcie_power_connectors=None))
    assert rules.psu_has_gpu_connectors(build).status == "unknown"


def test_psu_has_gpu_connectors_not_applicable_without_gpu():
    build = compatible_build(gpu=None)
    assert rules.psu_has_gpu_connectors(build).status == "pass"


# --- psu_fits_case ---


def test_psu_fits_case_pass():
    build = compatible_build()
    assert rules.psu_fits_case(build).status == "pass"


def test_psu_fits_case_fail():
    build = compatible_build(psu=with_specs(compatible_build().psu, form_factor="SFX"))
    assert rules.psu_fits_case(build).status == "fail"


def test_psu_fits_case_unknown():
    build = compatible_build(case=with_specs(compatible_build().case, psu_form_factor=None))
    assert rules.psu_fits_case(build).status == "unknown"


# --- storage_slots_available ---


def test_storage_slots_available_pass_nvme():
    build = compatible_build()
    assert rules.storage_slots_available(build).status == "pass"


def test_storage_slots_available_fail_nvme():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, m2_slots=0))
    assert rules.storage_slots_available(build).status == "fail"


def test_storage_slots_available_unknown_missing_slots():
    build = compatible_build(motherboard=with_specs(compatible_build().motherboard, m2_slots=None))
    assert rules.storage_slots_available(build).status == "unknown"


def test_storage_slots_available_unknown_missing_interface():
    build = compatible_build(storage=[with_specs(compatible_build().storage[0], interface=None)])
    assert rules.storage_slots_available(build).status == "unknown"


def test_storage_slots_available_pass_sata():
    build = compatible_build(storage=[with_specs(compatible_build().storage[0], interface="sata_ssd")])
    assert rules.storage_slots_available(build).status == "pass"


def test_storage_slots_available_unknown_missing_sata_ports():
    build = compatible_build(
        storage=[with_specs(compatible_build().storage[0], interface="sata_ssd")],
        motherboard=with_specs(compatible_build().motherboard, sata_ports=None),
    )
    assert rules.storage_slots_available(build).status == "unknown"


def test_storage_slots_available_fail_sata():
    build = compatible_build(
        storage=[with_specs(compatible_build().storage[0], interface="sata_ssd")],
        motherboard=with_specs(compatible_build().motherboard, sata_ports=0),
    )
    assert rules.storage_slots_available(build).status == "fail"


def test_storage_slots_available_pass_two_nvme_drives():
    build = compatible_build(
        storage=[storage_nvme_1tb(), storage_nvme_1tb()],
        motherboard=with_specs(compatible_build().motherboard, m2_slots=2),
    )
    assert rules.storage_slots_available(build).status == "pass"


def test_storage_slots_available_fail_two_nvme_drives_one_slot():
    build = compatible_build(storage=[storage_nvme_1tb(), storage_nvme_1tb()])
    assert rules.storage_slots_available(build).status == "fail"


def test_storage_slots_available_pass_mixed_nvme_and_sata():
    build = compatible_build(
        storage=[storage_nvme_1tb(), with_specs(storage_nvme_1tb(), interface="sata_ssd")]
    )
    assert rules.storage_slots_available(build).status == "pass"


# --- display_output_available ---


def test_display_output_available_pass_when_headless():
    build = compatible_build(gpu=None, cpu=with_specs(compatible_build().cpu, integrated_graphics=False))
    assert rules.display_output_available(build, headless=True).status == "pass"


def test_display_output_available_pass_with_gpu():
    build = compatible_build()
    assert rules.display_output_available(build, headless=False).status == "pass"


def test_display_output_available_pass_with_igpu():
    build = compatible_build(gpu=None, cpu=with_specs(compatible_build().cpu, integrated_graphics=True))
    assert rules.display_output_available(build, headless=False).status == "pass"


def test_display_output_available_fail_without_gpu_or_igpu():
    build = compatible_build(gpu=None, cpu=with_specs(compatible_build().cpu, integrated_graphics=False))
    assert rules.display_output_available(build, headless=False).status == "fail"


def test_display_output_available_unknown():
    build = compatible_build(gpu=None, cpu=with_specs(compatible_build().cpu, integrated_graphics=None))
    assert rules.display_output_available(build, headless=False).status == "unknown"
