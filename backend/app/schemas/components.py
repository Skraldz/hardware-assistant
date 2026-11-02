"""Pydantic v2 schemas for components, including per-category specs.

Specs fields are optional: a component can be entered manually with partial
knowledge, and the compatibility rules (Phase 2) treat a missing field as
"unknown" rather than pass/fail.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, create_model

from app.enums import Category, Condition, SpecsSource


class CpuSpecs(BaseModel):
    category: Literal["cpu"] = "cpu"
    socket: str | None = None
    cores: int | None = None
    threads: int | None = None
    tdp_w: int | None = None
    integrated_graphics: bool | None = None
    memory_type: list[Literal["DDR", "DDR2", "DDR3", "DDR4", "DDR5"]] | None = None


class MotherboardSpecs(BaseModel):
    category: Literal["motherboard"] = "motherboard"
    socket: str | None = None
    form_factor: Literal["ATX", "mATX", "ITX", "EATX"] | None = None
    memory_type: list[Literal["DDR", "DDR2", "DDR3", "DDR4", "DDR5"]] | None = None
    memory_slots: int | None = None
    max_memory_gb: int | None = None
    m2_slots: int | None = None
    sata_ports: int | None = None
    pcie_x16_slots: int | None = None


class RamSpecs(BaseModel):
    category: Literal["ram"] = "ram"
    memory_type: Literal["DDR", "DDR2", "DDR3", "DDR4", "DDR5"] | None = None
    capacity_gb_per_module: int | None = None
    modules: int | None = None
    speed_mts: int | None = None
    form: Literal["DIMM", "SODIMM"] | None = None


class GpuSpecs(BaseModel):
    category: Literal["gpu"] = "gpu"
    vram_gb: int | None = None
    tdp_w: int | None = None
    length_mm: int | None = None
    pcie_power_connectors: list[str] | None = None
    vendor: Literal["nvidia", "amd", "intel"] | None = None


class StorageSpecs(BaseModel):
    category: Literal["storage"] = "storage"
    interface: Literal["nvme", "sata_ssd", "sata_hdd"] | None = None
    capacity_gb: int | None = None
    form_factor: Literal["m2_2280", "2_5", "3_5"] | None = None


class PsuSpecs(BaseModel):
    category: Literal["psu"] = "psu"
    wattage_w: int | None = None
    form_factor: Literal["ATX", "SFX"] | None = None
    pcie_power_connectors: list[str] | None = None
    efficiency_rating: str | None = None


class CaseSpecs(BaseModel):
    category: Literal["case"] = "case"
    supported_form_factors: list[str] | None = None
    max_gpu_length_mm: int | None = None
    max_cooler_height_mm: int | None = None
    psu_form_factor: Literal["ATX", "SFX"] | None = None
    drive_bays_3_5: int | None = None
    drive_bays_2_5: int | None = None


class CoolerSpecs(BaseModel):
    category: Literal["cooler"] = "cooler"
    type: Literal["air", "aio"] | None = None
    supported_sockets: list[str] | None = None
    height_mm: int | None = None
    radiator_mm: int | None = None
    tdp_rating_w: int | None = None


ComponentSpecs = Annotated[
    CpuSpecs | MotherboardSpecs | RamSpecs | GpuSpecs | StorageSpecs | PsuSpecs | CaseSpecs | CoolerSpecs,
    Field(discriminator="category"),
]

# Reused by the pipeline (Phase 3) to turn a Component row's raw `specs`
# JSON dict back into the right category-specific spec model.
ComponentSpecsAdapter: TypeAdapter = TypeAdapter(ComponentSpecs)

# Reused by /api/components/extract (routers/components.py) to hand Ollama a
# flat, single-category schema instead of the full discriminated union above
# once the category is already known -- Ollama's structured-output grammar
# handles a plain object far more reliably than a `oneOf`/discriminator
# schema, which was leading the model to emit little beyond `category` itself.
SPEC_CLASS_BY_CATEGORY: dict[Category, type[BaseModel]] = {
    Category.CPU: CpuSpecs,
    Category.MOTHERBOARD: MotherboardSpecs,
    Category.RAM: RamSpecs,
    Category.GPU: GpuSpecs,
    Category.STORAGE: StorageSpecs,
    Category.PSU: PsuSpecs,
    Category.CASE: CaseSpecs,
    Category.COOLER: CoolerSpecs,
}


def _required_variant(
    model_cls: type[BaseModel], *, extra_fields: dict[str, type] | None = None
) -> type[BaseModel]:
    """A schema with the same fields/types as `model_cls`, but every field
    marked required -- the JSON key must be present, though its value may
    still be null. Used only as the schema handed to Ollama's
    structured-output `format` during extraction (routers/components.py).

    Every domain spec field has a default of None (so a component can be
    entered manually with partial knowledge), which means the JSON schema
    generated from the class as-is has no "required" list at all -- an
    empty `{}` already satisfies it. In practice this let the model skip
    straight past fields it wasn't fully confident about rather than
    committing to a value or an explicit null, extracting 1-2 fields out
    of 6 even when the rest were plainly stated in the given text. Forcing
    every key to be present closes that loophole without weakening the
    domain model itself (manual entry still needs genuinely optional
    fields, which this variant is never used for).

    `extra_fields` folds in fields that live outside `model_cls` (namely
    ComponentBase.release_year, which isn't part of any spec class -- see
    its own docstring) into this same structured-output call, rather than
    paying for a whole separate LLM round trip just for one more field.
    routers/components.py pops them back out before validating the rest
    against `model_cls`."""
    fields = {name: (field.annotation, ...) for name, field in model_cls.model_fields.items()}
    for name, annotation in (extra_fields or {}).items():
        fields[name] = (annotation, ...)
    return create_model(f"{model_cls.__name__}Extraction", **fields)


# Reused by /api/components/extract: the schema actually handed to Ollama's
# `format`, one "every field required" variant per category (see
# _required_variant), plus release_year (ComponentBase, not part of any
# spec class) folded in. The response is split back into release_year +
# the rest, which is re-validated against SPEC_CLASS_BY_CATEGORY afterwards
# to get back the real domain type.
EXTRACT_SCHEMA_BY_CATEGORY: dict[Category, type[BaseModel]] = {
    category: _required_variant(spec_class, extra_fields={"release_year": int | None})
    for category, spec_class in SPEC_CLASS_BY_CATEGORY.items()
}


class ComponentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=100)
    # When this specific product was released -- a property of the part
    # itself, not a technical capability, so it lives here rather than in
    # one of the category-specific spec classes above. Used by the recommend
    # pipeline to answer era-based requests ("hardware from 2010 or
    # earlier", "the oldest I have") and, more importantly, to sort each
    # category's candidates by relevance before the compatibility engine's
    # top_n cutoff -- see pipeline/recommend.py.
    release_year: int | None = None
    quantity: int = Field(ge=0, default=0)
    condition: Condition = Condition.NEW
    specs_source: SpecsSource = SpecsSource.MANUAL
    specs_verified: bool = False
    notes: str | None = None


class ComponentCreate(ComponentBase):
    specs: ComponentSpecs


class ComponentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=100)
    quantity: int | None = Field(default=None, ge=0)
    condition: Condition | None = None
    specs: ComponentSpecs | None = None
    specs_source: SpecsSource | None = None
    specs_verified: bool | None = None
    notes: str | None = None


class ComponentRead(ComponentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: Category
    specs: ComponentSpecs
    created_at: datetime
    updated_at: datetime


class ClearInventoryRequest(BaseModel):
    confirm: bool = False


class ClearInventoryResponse(BaseModel):
    deleted_components: int
    # Saved builds reference components by id and are meaningless once every
    # component is gone, so clearing the inventory clears these too.
    deleted_builds: int


class ReseedRequest(BaseModel):
    confirm: bool = False


class ReseedResponse(BaseModel):
    added: int
    # How many seed components were already present (matched by category +
    # name) and therefore left untouched -- reseeding adds what's missing,
    # it never duplicates or overwrites existing rows.
    skipped: int
