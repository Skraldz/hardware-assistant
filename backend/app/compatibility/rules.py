"""Compatibility rules (SPEC.md §6). Each rule is a pure function:

    def rule(build: Build) -> RuleResult

returning "pass", "fail", or "unknown" (missing data — never silently
treated as pass or fail). `display_output_available` is the one exception:
it also takes `headless`, since SPEC.md §5 says it is skipped for headless
use cases.
"""

from collections import Counter

from app.compatibility.types import Build, RuleResult
from app.config import get_settings


def cpu_socket_matches_board(build: Build) -> RuleResult:
    cpu_socket = build.cpu.specs.socket
    board_socket = build.motherboard.specs.socket
    if cpu_socket is None or board_socket is None:
        return RuleResult("unknown", "CPU or motherboard socket is not specified.")
    if cpu_socket == board_socket:
        return RuleResult("pass", f"CPU socket {cpu_socket} matches the motherboard.")
    return RuleResult(
        "fail", f"CPU socket {cpu_socket} does not match the motherboard's socket {board_socket}."
    )


def ram_type_matches(build: Build) -> RuleResult:
    ram_type = build.ram.specs.memory_type
    board_types = build.motherboard.specs.memory_type
    cpu_types = build.cpu.specs.memory_type
    if ram_type is None or board_types is None or cpu_types is None:
        return RuleResult(
            "unknown", "RAM type, motherboard memory type, or CPU memory type is not specified."
        )
    if ram_type in board_types and ram_type in cpu_types:
        return RuleResult("pass", f"{ram_type} is supported by both the CPU and motherboard.")
    return RuleResult(
        "fail",
        f"{ram_type} RAM is not supported by the motherboard ({board_types}) and/or CPU ({cpu_types}).",
    )


def ram_form_is_dimm(build: Build) -> RuleResult:
    form = build.ram.specs.form
    if form is None:
        return RuleResult("unknown", "RAM form factor is not specified.")
    if form == "DIMM":
        return RuleResult("pass", "RAM is DIMM, as required by desktop motherboards.")
    return RuleResult("fail", f"Desktop motherboards require DIMM, RAM is {form}.")


def ram_slots_sufficient(build: Build) -> RuleResult:
    modules = build.ram.specs.modules
    slots = build.motherboard.specs.memory_slots
    if modules is None or slots is None:
        return RuleResult("unknown", "Number of RAM modules or the motherboard's RAM slots is not specified.")
    if modules <= slots:
        return RuleResult("pass", f"{modules} module(s) fit in {slots} slot(s).")
    return RuleResult("fail", f"{modules} module(s) don't fit in only {slots} slot(s).")


def ram_capacity_within_board_max(build: Build) -> RuleResult:
    per_module = build.ram.specs.capacity_gb_per_module
    modules = build.ram.specs.modules
    max_gb = build.motherboard.specs.max_memory_gb
    if per_module is None or modules is None or max_gb is None:
        return RuleResult("unknown", "RAM capacity or the motherboard's max. memory is not specified.")
    total = per_module * modules
    if total <= max_gb:
        return RuleResult("pass", f"{total} GB RAM is within the motherboard's maximum ({max_gb} GB).")
    return RuleResult("fail", f"{total} GB RAM exceeds the motherboard's maximum ({max_gb} GB).")


def board_fits_case(build: Build) -> RuleResult:
    form_factor = build.motherboard.specs.form_factor
    supported = build.case.specs.supported_form_factors
    if form_factor is None or supported is None:
        return RuleResult(
            "unknown", "Motherboard form factor or the case's supported form factors is not specified."
        )
    if form_factor in supported:
        return RuleResult("pass", f"The case supports {form_factor}.")
    return RuleResult("fail", f"The case does not support the motherboard's form factor {form_factor}.")


def gpu_fits_case(build: Build) -> RuleResult:
    if build.gpu is None:
        return RuleResult("pass", "No GPU selected — this rule does not apply.")
    length = build.gpu.specs.length_mm
    max_length = build.case.specs.max_gpu_length_mm
    if length is None or max_length is None:
        return RuleResult("unknown", "GPU length or the case's max. GPU length is not specified.")
    if length <= max_length:
        return RuleResult("pass", f"GPU ({length} mm) fits in the case (max {max_length} mm).")
    return RuleResult("fail", f"GPU ({length} mm) is too long for the case (max {max_length} mm).")


def gpu_has_pcie_slot(build: Build) -> RuleResult:
    """A discrete GPU needs a PCIe x16 slot to sit in. `pcie_x16_slots` was
    modelled and populated from the start, but nothing read it, so a GPU
    paired with a slotless board passed every check (issue #5).

    Missing data gives "unknown" like every other rule rather than a quiet
    pass: a board whose slot count was never recorded probably has one, but
    "probably" is exactly what the unknown status exists to say out loud.
    """
    if build.gpu is None:
        return RuleResult("pass", "No GPU selected — this rule does not apply.")
    slots = build.motherboard.specs.pcie_x16_slots
    if slots is None:
        return RuleResult("unknown", "The motherboard's PCIe x16 slot count is not specified.")
    if slots < 1:
        return RuleResult("fail", "The motherboard has no PCIe x16 slot for the GPU.")
    return RuleResult("pass", f"The motherboard has {slots} PCIe x16 slot(s) for the GPU.")


def cooler_fits_case(build: Build) -> RuleResult:
    cooler_type = build.cooler.specs.type
    if cooler_type is None:
        return RuleResult("unknown", "Cooler type (air/aio) is not specified.")
    if cooler_type != "air":
        return RuleResult("pass", "This rule only applies to air coolers.")
    height = build.cooler.specs.height_mm
    max_height = build.case.specs.max_cooler_height_mm
    if height is None or max_height is None:
        return RuleResult("unknown", "Air cooler height or the case's max. cooler height is not specified.")
    if height <= max_height:
        return RuleResult("pass", f"Cooler ({height} mm) fits in the case (max {max_height} mm).")
    return RuleResult("fail", f"Cooler ({height} mm) is too tall for the case (max {max_height} mm).")


def cooler_supports_socket(build: Build) -> RuleResult:
    socket = build.cpu.specs.socket
    supported = build.cooler.specs.supported_sockets
    if socket is None or supported is None:
        return RuleResult("unknown", "CPU socket or the cooler's supported sockets is not specified.")
    if socket in supported:
        return RuleResult("pass", f"The cooler supports socket {socket}.")
    return RuleResult("fail", f"The cooler does not support CPU socket {socket}.")


def cooler_handles_tdp(build: Build) -> RuleResult:
    rating = build.cooler.specs.tdp_rating_w
    cpu_tdp = build.cpu.specs.tdp_w
    if rating is None or cpu_tdp is None:
        return RuleResult("unknown", "Cooler TDP rating or the CPU's TDP is not specified.")
    if rating >= cpu_tdp:
        return RuleResult("pass", f"Cooler ({rating} W) covers the CPU's {cpu_tdp} W.")
    return RuleResult("fail", f"Cooler ({rating} W) does not cover the CPU's {cpu_tdp} W.")


def psu_wattage_sufficient(build: Build) -> RuleResult:
    cpu_tdp = build.cpu.specs.tdp_w
    gpu_tdp = 0
    if build.gpu is not None:
        gpu_tdp = build.gpu.specs.tdp_w
        if gpu_tdp is None:
            return RuleResult("unknown", "GPU TDP is not specified.")
    psu_w = build.psu.specs.wattage_w
    if cpu_tdp is None or psu_w is None:
        return RuleResult("unknown", "CPU TDP or PSU wattage is not specified.")

    settings = get_settings()
    required = (cpu_tdp + gpu_tdp + settings.psu_base_watt_w) * settings.psu_safety_margin
    if psu_w >= required:
        return RuleResult("pass", f"PSU ({psu_w} W) covers the estimated requirement ({required:.0f} W).")
    return RuleResult("fail", f"PSU ({psu_w} W) does not cover the estimated requirement ({required:.0f} W).")


def psu_has_gpu_connectors(build: Build) -> RuleResult:
    if build.gpu is None:
        return RuleResult("pass", "No GPU selected — this rule does not apply.")
    gpu_connectors = build.gpu.specs.pcie_power_connectors
    psu_connectors = build.psu.specs.pcie_power_connectors
    if gpu_connectors is None or psu_connectors is None:
        return RuleResult("unknown", "GPU or PSU power connectors are not specified.")
    required = Counter(gpu_connectors)
    available = Counter(psu_connectors)
    if all(available.get(connector, 0) >= count for connector, count in required.items()):
        return RuleResult("pass", "The PSU has the power connectors the GPU requires.")
    return RuleResult(
        "fail", f"PSU ({psu_connectors}) is missing one of the GPU's power connectors ({gpu_connectors})."
    )


def psu_fits_case(build: Build) -> RuleResult:
    psu_form_factor = build.psu.specs.form_factor
    case_psu_form_factor = build.case.specs.psu_form_factor
    if psu_form_factor is None or case_psu_form_factor is None:
        return RuleResult("unknown", "PSU form factor or the case's PSU form factor is not specified.")
    if psu_form_factor == case_psu_form_factor:
        return RuleResult("pass", f"The case supports {psu_form_factor} PSUs.")
    return RuleResult(
        "fail", f"The case requires a {case_psu_form_factor} PSU, this one is {psu_form_factor}."
    )


def storage_slots_available(build: Build) -> RuleResult:
    """A build may hold multiple drives (engine.py's MAX_STORAGE_DRIVES) --
    counts them by interface (NVMe drives need M.2 slots, SATA SSDs/HDDs
    need SATA ports) and checks each count against the motherboard's
    matching slot count."""
    nvme_count = 0
    sata_count = 0
    for drive in build.storage:
        interface = drive.specs.interface
        if interface is None:
            return RuleResult("unknown", "A storage device's interface is not specified.")
        if interface == "nvme":
            nvme_count += 1
        else:
            sata_count += 1

    m2_slots = build.motherboard.specs.m2_slots
    sata_ports = build.motherboard.specs.sata_ports
    if nvme_count and m2_slots is None:
        return RuleResult("unknown", "Motherboard's number of M.2 slots is not specified.")
    if sata_count and sata_ports is None:
        return RuleResult("unknown", "Motherboard's number of SATA ports is not specified.")

    if nvme_count > (m2_slots or 0):
        return RuleResult(
            "fail", f"{nvme_count} NVMe drive(s) don't fit in the motherboard's {m2_slots} M.2 slot(s)."
        )
    if sata_count > (sata_ports or 0):
        return RuleResult(
            "fail", f"{sata_count} SATA drive(s) don't fit in the motherboard's {sata_ports} SATA port(s)."
        )

    parts = []
    if nvme_count:
        parts.append(f"{nvme_count} NVMe drive(s) in {m2_slots} M.2 slot(s)")
    if sata_count:
        parts.append(f"{sata_count} SATA drive(s) in {sata_ports} SATA port(s)")
    return RuleResult("pass", f"The motherboard fits {' and '.join(parts)}.")


def display_output_available(build: Build, *, headless: bool = False) -> RuleResult:
    if headless:
        return RuleResult("pass", "Headless — no display output needed.")
    if build.gpu is not None:
        return RuleResult("pass", "GPU provides display output.")
    igpu = build.cpu.specs.integrated_graphics
    if igpu is None:
        return RuleResult("unknown", "It is not specified whether the CPU has integrated graphics.")
    if igpu:
        return RuleResult("pass", "The CPU has integrated graphics.")
    return RuleResult("fail", "No GPU, and the CPU does not have integrated graphics — no display output.")


ALL_RULES = [
    cpu_socket_matches_board,
    ram_type_matches,
    ram_form_is_dimm,
    ram_slots_sufficient,
    ram_capacity_within_board_max,
    board_fits_case,
    gpu_fits_case,
    gpu_has_pcie_slot,
    cooler_fits_case,
    cooler_supports_socket,
    cooler_handles_tdp,
    psu_wattage_sufficient,
    psu_has_gpu_connectors,
    psu_fits_case,
    storage_slots_available,
]
