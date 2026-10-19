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
        return RuleResult("unknown", "CPU- eller bundkort-socket er ikke angivet.")
    if cpu_socket == board_socket:
        return RuleResult("pass", f"CPU-socket {cpu_socket} matcher bundkortet.")
    return RuleResult("fail", f"CPU-socket {cpu_socket} passer ikke med bundkortets socket {board_socket}.")


def ram_type_matches(build: Build) -> RuleResult:
    ram_type = build.ram.specs.memory_type
    board_types = build.motherboard.specs.memory_type
    cpu_types = build.cpu.specs.memory_type
    if ram_type is None or board_types is None or cpu_types is None:
        return RuleResult("unknown", "RAM-type, bundkort- eller CPU-hukommelsestype er ikke angivet.")
    if ram_type in board_types and ram_type in cpu_types:
        return RuleResult("pass", f"{ram_type} understøttes af både CPU og bundkort.")
    return RuleResult(
        "fail",
        f"{ram_type}-RAM understøttes ikke af bundkort ({board_types}) og/eller CPU ({cpu_types}).",
    )


def ram_form_is_dimm(build: Build) -> RuleResult:
    form = build.ram.specs.form
    if form is None:
        return RuleResult("unknown", "RAM-formfaktor er ikke angivet.")
    if form == "DIMM":
        return RuleResult("pass", "RAM er DIMM, som desktop-bundkort kræver.")
    return RuleResult("fail", f"Desktop-bundkort kræver DIMM, RAM er {form}.")


def ram_slots_sufficient(build: Build) -> RuleResult:
    modules = build.ram.specs.modules
    slots = build.motherboard.specs.memory_slots
    if modules is None or slots is None:
        return RuleResult("unknown", "Antal RAM-moduler eller bundkortets RAM-slots er ikke angivet.")
    if modules <= slots:
        return RuleResult("pass", f"{modules} modul(er) passer i {slots} slot(s).")
    return RuleResult("fail", f"{modules} modul(er) passer ikke i kun {slots} slot(s).")


def ram_capacity_within_board_max(build: Build) -> RuleResult:
    per_module = build.ram.specs.capacity_gb_per_module
    modules = build.ram.specs.modules
    max_gb = build.motherboard.specs.max_memory_gb
    if per_module is None or modules is None or max_gb is None:
        return RuleResult("unknown", "RAM-kapacitet eller bundkortets max. hukommelse er ikke angivet.")
    total = per_module * modules
    if total <= max_gb:
        return RuleResult("pass", f"{total} GB RAM er inden for bundkortets maks ({max_gb} GB).")
    return RuleResult("fail", f"{total} GB RAM overstiger bundkortets maks ({max_gb} GB).")


def board_fits_case(build: Build) -> RuleResult:
    form_factor = build.motherboard.specs.form_factor
    supported = build.case.specs.supported_form_factors
    if form_factor is None or supported is None:
        return RuleResult(
            "unknown", "Bundkortets formfaktor eller kabinettets støttede formfaktorer er ikke angivet."
        )
    if form_factor in supported:
        return RuleResult("pass", f"Kabinettet understøtter {form_factor}.")
    return RuleResult("fail", f"Kabinettet understøtter ikke bundkortets formfaktor {form_factor}.")


def gpu_fits_case(build: Build) -> RuleResult:
    if build.gpu is None:
        return RuleResult("pass", "Intet GPU valgt — reglen er ikke relevant.")
    length = build.gpu.specs.length_mm
    max_length = build.case.specs.max_gpu_length_mm
    if length is None or max_length is None:
        return RuleResult("unknown", "GPU-længde eller kabinettets maks. GPU-længde er ikke angivet.")
    if length <= max_length:
        return RuleResult("pass", f"GPU ({length} mm) passer i kabinettet (maks {max_length} mm).")
    return RuleResult("fail", f"GPU ({length} mm) er for lang til kabinettet (maks {max_length} mm).")


def cooler_fits_case(build: Build) -> RuleResult:
    cooler_type = build.cooler.specs.type
    if cooler_type is None:
        return RuleResult("unknown", "Kølertype (air/aio) er ikke angivet.")
    if cooler_type != "air":
        return RuleResult("pass", "Reglen gælder kun luftkølere.")
    height = build.cooler.specs.height_mm
    max_height = build.case.specs.max_cooler_height_mm
    if height is None or max_height is None:
        return RuleResult("unknown", "Luftkølerens højde eller kabinettets maks. kølerhøjde er ikke angivet.")
    if height <= max_height:
        return RuleResult("pass", f"Køler ({height} mm) passer i kabinettet (maks {max_height} mm).")
    return RuleResult("fail", f"Køler ({height} mm) er for høj til kabinettet (maks {max_height} mm).")


def cooler_supports_socket(build: Build) -> RuleResult:
    socket = build.cpu.specs.socket
    supported = build.cooler.specs.supported_sockets
    if socket is None or supported is None:
        return RuleResult("unknown", "CPU-socket eller kølerens støttede sockets er ikke angivet.")
    if socket in supported:
        return RuleResult("pass", f"Køleren understøtter socket {socket}.")
    return RuleResult("fail", f"Køleren understøtter ikke CPU-socket {socket}.")


def cooler_handles_tdp(build: Build) -> RuleResult:
    rating = build.cooler.specs.tdp_rating_w
    cpu_tdp = build.cpu.specs.tdp_w
    if rating is None or cpu_tdp is None:
        return RuleResult("unknown", "Kølerens TDP-rating eller CPU'ens TDP er ikke angivet.")
    if rating >= cpu_tdp:
        return RuleResult("pass", f"Køler ({rating} W) dækker CPU'ens {cpu_tdp} W.")
    return RuleResult("fail", f"Køler ({rating} W) dækker ikke CPU'ens {cpu_tdp} W.")


def psu_wattage_sufficient(build: Build) -> RuleResult:
    cpu_tdp = build.cpu.specs.tdp_w
    gpu_tdp = 0
    if build.gpu is not None:
        gpu_tdp = build.gpu.specs.tdp_w
        if gpu_tdp is None:
            return RuleResult("unknown", "GPU'ens TDP er ikke angivet.")
    psu_w = build.psu.specs.wattage_w
    if cpu_tdp is None or psu_w is None:
        return RuleResult("unknown", "CPU'ens TDP eller PSU'ens watt er ikke angivet.")

    settings = get_settings()
    required = (cpu_tdp + gpu_tdp + settings.psu_base_watt_w) * settings.psu_safety_margin
    if psu_w >= required:
        return RuleResult("pass", f"PSU ({psu_w} W) dækker det estimerede behov ({required:.0f} W).")
    return RuleResult("fail", f"PSU ({psu_w} W) dækker ikke det estimerede behov ({required:.0f} W).")


def psu_has_gpu_connectors(build: Build) -> RuleResult:
    if build.gpu is None:
        return RuleResult("pass", "Intet GPU valgt — reglen er ikke relevant.")
    gpu_connectors = build.gpu.specs.pcie_power_connectors
    psu_connectors = build.psu.specs.pcie_power_connectors
    if gpu_connectors is None or psu_connectors is None:
        return RuleResult("unknown", "GPU'ens eller PSU'ens strømstik er ikke angivet.")
    required = Counter(gpu_connectors)
    available = Counter(psu_connectors)
    if all(available.get(connector, 0) >= count for connector, count in required.items()):
        return RuleResult("pass", "PSU har de strømstik, GPU'en kræver.")
    return RuleResult("fail", f"PSU ({psu_connectors}) mangler et af GPU'ens strømstik ({gpu_connectors}).")


def psu_fits_case(build: Build) -> RuleResult:
    psu_form_factor = build.psu.specs.form_factor
    case_psu_form_factor = build.case.specs.psu_form_factor
    if psu_form_factor is None or case_psu_form_factor is None:
        return RuleResult("unknown", "PSU'ens eller kabinettets PSU-formfaktor er ikke angivet.")
    if psu_form_factor == case_psu_form_factor:
        return RuleResult("pass", f"Kabinettet understøtter {psu_form_factor}-PSU'er.")
    return RuleResult("fail", f"Kabinettet kræver en {case_psu_form_factor}-PSU, denne er {psu_form_factor}.")


def storage_slots_available(build: Build) -> RuleResult:
    interface = build.storage.specs.interface
    if interface is None:
        return RuleResult("unknown", "Lagerenhedens interface er ikke angivet.")
    if interface == "nvme":
        slots = build.motherboard.specs.m2_slots
        if slots is None:
            return RuleResult("unknown", "Bundkortets antal M.2-slots er ikke angivet.")
        if slots >= 1:
            return RuleResult("pass", f"Bundkortet har {slots} M.2-slot(s) til NVMe-drevet.")
        return RuleResult("fail", "Bundkortet har ingen M.2-slots til NVMe-drevet.")
    ports = build.motherboard.specs.sata_ports
    if ports is None:
        return RuleResult("unknown", "Bundkortets antal SATA-porte er ikke angivet.")
    if ports >= 1:
        return RuleResult("pass", f"Bundkortet har {ports} SATA-port(e) til drevet.")
    return RuleResult("fail", "Bundkortet har ingen SATA-porte til drevet.")


def display_output_available(build: Build, *, headless: bool = False) -> RuleResult:
    if headless:
        return RuleResult("pass", "Headless — skærmudgang er ikke nødvendig.")
    if build.gpu is not None:
        return RuleResult("pass", "GPU leverer skærmudgang.")
    igpu = build.cpu.specs.integrated_graphics
    if igpu is None:
        return RuleResult("unknown", "Det er ikke angivet, om CPU'en har integreret grafik.")
    if igpu:
        return RuleResult("pass", "CPU'en har integreret grafik.")
    return RuleResult("fail", "Intet GPU, og CPU'en har ikke integreret grafik — ingen skærmudgang.")


ALL_RULES = [
    cpu_socket_matches_board,
    ram_type_matches,
    ram_form_is_dimm,
    ram_slots_sufficient,
    ram_capacity_within_board_max,
    board_fits_case,
    gpu_fits_case,
    cooler_fits_case,
    cooler_supports_socket,
    cooler_handles_tdp,
    psu_wattage_sufficient,
    psu_has_gpu_connectors,
    psu_fits_case,
    storage_slots_available,
]
