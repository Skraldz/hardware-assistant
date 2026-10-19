"""ProjectRequirements: the LLM's interpretation of the user's free-text
project description (SPEC.md §5 step 1). Every field has a safe default so a
fallback instance (used when the LLM's output can't be validated even after
one retry) is just `ProjectRequirements(use_case=<original prompt>)`.
"""

from pydantic import BaseModel, Field

from app.enums import Category


class ProjectRequirements(BaseModel):
    use_case: str
    headless: bool = False
    required_categories: list[Category] = Field(default_factory=list)
    min_vram_gb: int | None = None
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    min_cpu_cores: int | None = None
    prefer_low_power: bool = False
    prefer_small_form_factor: bool = False
    notes: str = ""


def fallback_requirements(user_prompt: str) -> ProjectRequirements:
    """Conservative defaults used when the LLM's output never validates
    (SPEC.md §5 step 1: "fallback til konservative defaults + advarsel")."""
    return ProjectRequirements(
        use_case=user_prompt,
        notes="LLM-fortolkning af projektbeskrivelsen fejlede; bruger konservative standardkrav.",
    )
