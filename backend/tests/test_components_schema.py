"""Tests for the extraction-only "every field required" schema variants
(schemas/components.py's EXTRACT_SCHEMA_BY_CATEGORY) -- the fix for Ollama
extracting only 1-2 fields out of 6 even when the rest were plainly stated
in the given text, because every domain spec field has a default and the
resulting JSON schema had no "required" list at all."""

import pytest
from pydantic import ValidationError

from app.enums import Category
from app.schemas.components import EXTRACT_SCHEMA_BY_CATEGORY, SPEC_CLASS_BY_CATEGORY, GpuSpecs


def test_extract_schema_requires_every_field_but_allows_null():
    schema = EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU].model_json_schema()

    assert set(schema["required"]) == set(GpuSpecs.model_fields.keys()) | {"release_year"}
    # vram_gb may still be null -- the key must be present, not the value.
    parsed = EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU].model_validate(
        {
            "category": "gpu",
            "vram_gb": None,
            "tdp_w": None,
            "length_mm": None,
            "pcie_power_connectors": None,
            "vendor": "nvidia",
            "release_year": None,
        }
    )
    assert parsed.vram_gb is None
    assert parsed.vendor == "nvidia"


def test_extract_schema_rejects_a_missing_key():
    with pytest.raises(ValidationError):
        EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU].model_validate({"category": "gpu", "vendor": "nvidia"})


def test_every_category_has_an_extract_schema():
    assert set(EXTRACT_SCHEMA_BY_CATEGORY.keys()) == set(SPEC_CLASS_BY_CATEGORY.keys())


def test_extracted_data_round_trips_into_the_real_domain_spec_class():
    extracted = EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU].model_validate(
        {
            "category": "gpu",
            "vram_gb": 8,
            "tdp_w": 170,
            "length_mm": 240,
            "pcie_power_connectors": ["8-pin"],
            "vendor": "nvidia",
            "release_year": 2019,
        }
    )

    specs = GpuSpecs.model_validate(extracted.model_dump())

    assert isinstance(specs, GpuSpecs)
    assert specs.vram_gb == 8
