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
    # Set when the user asks for a build that's no more powerful than
    # necessary (e.g. "but not more powerful than that") -- the deterministic
    # scorer (pipeline/recommend.py) then prefers the build that's just
    # sufficient for the stated goal over the most capable one available,
    # and the ranking LLM is instructed (llm/prompts.py) to do the same.
    prefer_minimal_spec: bool = False
    notes: str = ""


def fallback_requirements(user_prompt: str) -> ProjectRequirements:
    """Conservative defaults used when the LLM's output never validates
    (SPEC.md §5 step 1: fall back to conservative defaults + a warning)."""
    return ProjectRequirements(
        use_case=user_prompt,
        notes="LLM interpretation of the project description failed; using conservative defaults.",
    )
