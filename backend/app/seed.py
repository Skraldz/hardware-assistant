"""Demo/test seed data: ~25 realistic components, incl. the user's real PC and
enough variety (sockets, form factors, wattages) to produce both compatible
builds and deliberate incompatibilities (e.g. AM4 CPUs vs. LGA1700 boards) for
the compatibility engine (Phase 2) to catch.

Idempotent: does nothing if the components table already has rows, so it can
safely run on every container start.
"""

from app.db import Base, SessionLocal, engine
from app.enums import Category, Condition, SpecsSource
from app.models import Component

SEED_COMPONENTS: list[dict] = [
    # --- Real hardware (mirrors the author's own PC) ---
    {
        "category": Category.CPU,
        "name": "AMD Ryzen 5 3600",
        "manufacturer": "AMD",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "cpu",
            "socket": "AM4",
            "cores": 6,
            "threads": 12,
            "tdp_w": 65,
            "integrated_graphics": False,
            "memory_type": ["DDR4"],
        },
        "notes": "Ejet hardware.",
    },
    {
        "category": Category.MOTHERBOARD,
        "name": "ASUS TUF B450M-PLUS GAMING",
        "manufacturer": "ASUS",
        "quantity": 1,
        "condition": Condition.USED,
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
        "notes": "Ejet hardware.",
    },
    {
        "category": Category.RAM,
        "name": "Corsair Vengeance LPX 16GB (2x8GB) DDR4-3000",
        "manufacturer": "Corsair",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "speed_mts": 3000,
            "form": "DIMM",
        },
        "notes": "Ejet hardware (part CMW16GX4M2D3000C16; rated hastighed brugt, kørte uden XMP).",
    },
    {
        "category": Category.GPU,
        "name": "NVIDIA GeForce RTX 2060 6GB",
        "manufacturer": "NVIDIA",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "gpu",
            "vram_gb": 6,
            "tdp_w": 160,
            "length_mm": 229,
            "pcie_power_connectors": ["8-pin"],
            "vendor": "nvidia",
        },
        "notes": "Ejet hardware.",
    },
    {
        "category": Category.STORAGE,
        "name": "Intel SSDPEKNW010T8 1TB NVMe",
        "manufacturer": "Intel",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "storage",
            "interface": "nvme",
            "capacity_gb": 1000,
            "form_factor": "m2_2280",
        },
        "notes": "Ejet hardware.",
    },
    {
        "category": Category.PSU,
        "name": "Corsair RM650x",
        "manufacturer": "Corsair",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "psu",
            "wattage_w": 650,
            "form_factor": "ATX",
            "pcie_power_connectors": ["8-pin", "8-pin"],
            "efficiency_rating": "80+ Gold",
        },
        "notes": "Fabrikeret eksempel til seed-data (ikke en nøjagtig opgørelse af den faktisk ejede PSU).",
    },
    {
        "category": Category.CASE,
        "name": "NZXT H510",
        "manufacturer": "NZXT",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "case",
            "supported_form_factors": ["ATX", "mATX", "ITX"],
            "max_gpu_length_mm": 381,
            "max_cooler_height_mm": 165,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 2,
            "drive_bays_2_5": 2,
        },
        "notes": "Fabrikeret eksempel til seed-data (ikke det faktisk ejede kabinet).",
    },
    {
        "category": Category.COOLER,
        "name": "AMD Wraith Stealth",
        "manufacturer": "AMD",
        "quantity": 1,
        "condition": Condition.USED,
        "specs": {
            "category": "cooler",
            "type": "air",
            "supported_sockets": ["AM4"],
            "height_mm": 54,
            "tdp_rating_w": 65,
        },
        "notes": "Medfølger Ryzen 5 3600 i boks.",
    },
    # --- Supplementary fictional hardware (variety + a deliberate socket mismatch) ---
    {
        "category": Category.CPU,
        "name": "Intel Core i5-12400",
        "manufacturer": "Intel",
        "quantity": 2,
        "condition": Condition.NEW,
        "specs": {
            "category": "cpu",
            "socket": "LGA1700",
            "cores": 6,
            "threads": 12,
            "tdp_w": 65,
            "integrated_graphics": True,
            "memory_type": ["DDR4", "DDR5"],
        },
    },
    {
        "category": Category.CPU,
        "name": "AMD Ryzen 7 5800X3D",
        "manufacturer": "AMD",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "cpu",
            "socket": "AM4",
            "cores": 8,
            "threads": 16,
            "tdp_w": 105,
            "integrated_graphics": False,
            "memory_type": ["DDR4"],
        },
    },
    {
        "category": Category.CPU,
        "name": "Intel Core i9-13900K",
        "manufacturer": "Intel",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "cpu",
            "socket": "LGA1700",
            "cores": 24,
            "threads": 32,
            "tdp_w": 125,
            "integrated_graphics": True,
            "memory_type": ["DDR4", "DDR5"],
        },
    },
    {
        "category": Category.MOTHERBOARD,
        "name": "MSI PRO B660M-A",
        "manufacturer": "MSI",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "motherboard",
            "socket": "LGA1700",
            "form_factor": "mATX",
            "memory_type": ["DDR4"],
            "memory_slots": 4,
            "max_memory_gb": 128,
            "m2_slots": 2,
            "sata_ports": 4,
            "pcie_x16_slots": 1,
        },
    },
    {
        "category": Category.MOTHERBOARD,
        "name": "Gigabyte Z790 AORUS ELITE",
        "manufacturer": "Gigabyte",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "motherboard",
            "socket": "LGA1700",
            "form_factor": "ATX",
            "memory_type": ["DDR5"],
            "memory_slots": 4,
            "max_memory_gb": 128,
            "m2_slots": 3,
            "sata_ports": 6,
            "pcie_x16_slots": 2,
        },
    },
    {
        "category": Category.MOTHERBOARD,
        "name": "ASRock X570 Phantom Gaming 4",
        "manufacturer": "ASRock",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "motherboard",
            "socket": "AM4",
            "form_factor": "ATX",
            "memory_type": ["DDR4"],
            "memory_slots": 4,
            "max_memory_gb": 128,
            "m2_slots": 2,
            "sata_ports": 8,
            "pcie_x16_slots": 2,
        },
    },
    {
        "category": Category.RAM,
        "name": "Kingston Fury Beast 16GB (2x8GB) DDR5-5600",
        "manufacturer": "Kingston",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "ram",
            "memory_type": "DDR5",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "speed_mts": 5600,
            "form": "DIMM",
        },
    },
    {
        "category": Category.RAM,
        "name": "Crucial Ballistix 32GB (2x16GB) DDR4-3200",
        "manufacturer": "Crucial",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 16,
            "modules": 2,
            "speed_mts": 3200,
            "form": "DIMM",
        },
    },
    {
        "category": Category.RAM,
        "name": "Corsair Vengeance SO-DIMM 16GB (2x8GB) DDR4-3200",
        "manufacturer": "Corsair",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "ram",
            "memory_type": "DDR4",
            "capacity_gb_per_module": 8,
            "modules": 2,
            "speed_mts": 3200,
            "form": "SODIMM",
        },
        "notes": "Laptop-RAM; forkert formfaktor til et desktop-bundkort (tester ram_form_is_dimm-reglen).",
    },
    {
        "category": Category.GPU,
        "name": "NVIDIA GeForce RTX 4070",
        "manufacturer": "NVIDIA",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "gpu",
            "vram_gb": 12,
            "tdp_w": 200,
            "length_mm": 244,
            "pcie_power_connectors": ["16-pin"],
            "vendor": "nvidia",
        },
    },
    {
        "category": Category.GPU,
        "name": "AMD Radeon RX 6600",
        "manufacturer": "AMD",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "gpu",
            "vram_gb": 8,
            "tdp_w": 132,
            "length_mm": 190,
            "pcie_power_connectors": ["8-pin"],
            "vendor": "amd",
        },
    },
    {
        "category": Category.STORAGE,
        "name": "Samsung 970 EVO Plus 500GB NVMe",
        "manufacturer": "Samsung",
        "quantity": 0,
        "condition": Condition.USED,
        "specs": {
            "category": "storage",
            "interface": "nvme",
            "capacity_gb": 500,
            "form_factor": "m2_2280",
        },
        "notes": "Solgt videre; quantity=0 tester at ude-af-lager komponenter udelukkes fra builds.",
    },
    {
        "category": Category.STORAGE,
        "name": "Seagate Barracuda 2TB",
        "manufacturer": "Seagate",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "storage",
            "interface": "sata_hdd",
            "capacity_gb": 2000,
            "form_factor": "3_5",
        },
    },
    {
        "category": Category.PSU,
        "name": "Corsair SF750",
        "manufacturer": "Corsair",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "psu",
            "wattage_w": 750,
            "form_factor": "SFX",
            "pcie_power_connectors": ["12-pin", "8-pin"],
            "efficiency_rating": "80+ Platinum",
        },
    },
    {
        "category": Category.PSU,
        "name": "EVGA 500W Bronze",
        "manufacturer": "EVGA",
        "quantity": 1,
        "condition": Condition.FAULTY,
        "specs": {
            "category": "psu",
            "wattage_w": 500,
            "form_factor": "ATX",
            "pcie_power_connectors": ["6-pin"],
            "efficiency_rating": "80+ Bronze",
        },
        "notes": "Markeret faulty; tester at defekte komponenter altid udelukkes fra builds.",
    },
    {
        "category": Category.CASE,
        "name": "Fractal Design Node 304",
        "manufacturer": "Fractal Design",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "case",
            "supported_form_factors": ["ITX"],
            "max_gpu_length_mm": 310,
            "max_cooler_height_mm": 65,
            "psu_form_factor": "SFX",
            "drive_bays_3_5": 3,
            "drive_bays_2_5": 2,
        },
        "notes": "Lille ITX-kabinet; tester board_fits_case/cooler_fits_case/psu_fits_case for ATX-dele.",
    },
    {
        "category": Category.CASE,
        "name": "Lian Li O11 Dynamic",
        "manufacturer": "Lian Li",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "case",
            "supported_form_factors": ["ATX", "mATX", "ITX", "EATX"],
            "max_gpu_length_mm": 420,
            "max_cooler_height_mm": 155,
            "psu_form_factor": "ATX",
            "drive_bays_3_5": 2,
            "drive_bays_2_5": 4,
        },
    },
    {
        "category": Category.COOLER,
        "name": "Noctua NH-D15",
        "manufacturer": "Noctua",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "cooler",
            "type": "air",
            "supported_sockets": ["AM4", "AM5", "LGA1700"],
            "height_mm": 165,
            "tdp_rating_w": 220,
        },
        "notes": "For høj til Fractal Design Node 304 (65mm maks); tester cooler_fits_case.",
    },
    {
        "category": Category.COOLER,
        "name": "Corsair H100i 240mm AIO",
        "manufacturer": "Corsair",
        "quantity": 1,
        "condition": Condition.NEW,
        "specs": {
            "category": "cooler",
            "type": "aio",
            "supported_sockets": ["AM4", "AM5", "LGA1700", "LGA1200"],
            "radiator_mm": 240,
            "tdp_rating_w": 250,
        },
    },
]


def seed(db) -> int:
    if db.query(Component).first() is not None:
        return 0
    for item in SEED_COMPONENTS:
        db.add(
            Component(
                specs_source=SpecsSource.MANUAL,
                specs_verified=True,
                **item,
            )
        )
    db.commit()
    return len(SEED_COMPONENTS)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = seed(db)
        if created:
            print(f"Seeded {created} components.")
        else:
            print("Components already exist, skipping seed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
