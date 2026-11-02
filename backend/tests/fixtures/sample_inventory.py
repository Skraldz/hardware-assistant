"""A small, hand-crafted, fully-compatible baseline build used by
test_rules.py and test_engine.py. Deliberately separate from app/seed.py,
which is large and realistic for the demo, not minimal for assertions.
"""

from app.compatibility.types import Build, CandidateComponent
from app.schemas.components import (
    CaseSpecs,
    CoolerSpecs,
    CpuSpecs,
    GpuSpecs,
    MotherboardSpecs,
    PsuSpecs,
    RamSpecs,
    StorageSpecs,
)


def cpu_ryzen_5_3600() -> CandidateComponent:
    return CandidateComponent(
        id=1,
        name="AMD Ryzen 5 3600",
        specs=CpuSpecs(
            socket="AM4", cores=6, threads=12, tdp_w=65, integrated_graphics=False, memory_type=["DDR4"]
        ),
    )


def motherboard_b450m() -> CandidateComponent:
    return CandidateComponent(
        id=2,
        name="ASUS TUF B450M-PLUS GAMING",
        specs=MotherboardSpecs(
            socket="AM4",
            form_factor="mATX",
            memory_type=["DDR4"],
            memory_slots=4,
            max_memory_gb=64,
            m2_slots=1,
            sata_ports=4,
            pcie_x16_slots=1,
        ),
    )


def ram_corsair_16gb() -> CandidateComponent:
    return CandidateComponent(
        id=3,
        name="Corsair Vengeance 16GB DDR4-3000",
        specs=RamSpecs(memory_type="DDR4", capacity_gb_per_module=8, modules=2, speed_mts=3000, form="DIMM"),
    )


def gpu_rtx_2060() -> CandidateComponent:
    return CandidateComponent(
        id=4,
        name="NVIDIA GeForce RTX 2060",
        specs=GpuSpecs(vram_gb=6, tdp_w=160, length_mm=229, pcie_power_connectors=["8-pin"], vendor="nvidia"),
    )


def storage_nvme_1tb() -> CandidateComponent:
    return CandidateComponent(
        id=5,
        name="Intel SSDPEKNW010T8 1TB NVMe",
        specs=StorageSpecs(interface="nvme", capacity_gb=1000, form_factor="m2_2280"),
    )


def psu_650w() -> CandidateComponent:
    return CandidateComponent(
        id=6,
        name="Corsair RM650x",
        specs=PsuSpecs(
            wattage_w=650,
            form_factor="ATX",
            pcie_power_connectors=["8-pin", "8-pin"],
            efficiency_rating="80+ Gold",
        ),
    )


def case_atx() -> CandidateComponent:
    return CandidateComponent(
        id=7,
        name="NZXT H510",
        specs=CaseSpecs(
            supported_form_factors=["ATX", "mATX", "ITX"],
            max_gpu_length_mm=381,
            max_cooler_height_mm=165,
            psu_form_factor="ATX",
            drive_bays_3_5=2,
            drive_bays_2_5=2,
        ),
    )


def cooler_wraith_stealth() -> CandidateComponent:
    return CandidateComponent(
        id=8,
        name="AMD Wraith Stealth",
        specs=CoolerSpecs(type="air", supported_sockets=["AM4"], height_mm=54, tdp_rating_w=65),
    )


def compatible_build(**overrides) -> Build:
    defaults: dict = {
        "cpu": cpu_ryzen_5_3600(),
        "motherboard": motherboard_b450m(),
        "ram": ram_corsair_16gb(),
        "storage": [storage_nvme_1tb()],
        "psu": psu_650w(),
        "case": case_atx(),
        "cooler": cooler_wraith_stealth(),
        "gpu": gpu_rtx_2060(),
    }
    defaults.update(overrides)
    return Build(**defaults)


def with_specs(component: CandidateComponent, **updates) -> CandidateComponent:
    """Return a copy of `component` with some spec fields overridden."""
    return CandidateComponent(
        id=component.id,
        name=component.name,
        specs=component.specs.model_copy(update=updates),
        release_year=component.release_year,
    )


def with_release_year(component: CandidateComponent, release_year: int | None) -> CandidateComponent:
    """Return a copy of `component` with its release_year overridden."""
    return CandidateComponent(
        id=component.id, name=component.name, specs=component.specs, release_year=release_year
    )
