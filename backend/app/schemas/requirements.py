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
    # Hard era bounds (e.g. "hardware from 2010 or earlier", "newer than
    # 2020") -- a component missing release_year fails these the same way
    # missing specs already fail min_vram_gb/min_ram_gb/etc. (pipeline/
    # recommend.py's _meets_hard_requirements): a hard requirement the user
    # actually asked for shouldn't be satisfied by a guess.
    #
    # The field names alone were not enough: qwen2.5:7b-instruct consistently
    # read "from 2010 or earlier" as released_no_earlier_than=2010 -- the exact
    # inverse -- which both admitted newer hardware and excluded the genuinely
    # old parts the user asked for. These descriptions reach the model: they
    # are part of model_json_schema(), which is passed to Ollama as `format`,
    # so the mapping travels with the schema rather than relying on the
    # system prompt alone.
    released_no_later_than: int | None = Field(
        default=None,
        description=(
            "UPPER bound on a component's release year: nothing released AFTER this year. "
            'Use for "2010 or earlier", "nothing newer than 2010" (both -> 2010).'
        ),
    )
    released_no_earlier_than: int | None = Field(
        default=None,
        description=(
            "LOWER bound on a component's release year: nothing released BEFORE this year. "
            'Use for "2020 or newer", "nothing older than 2020" (both -> 2020).'
        ),
    )
    prefer_low_power: bool = False
    prefer_small_form_factor: bool = False
    # Set when the user wants the oldest/newest hardware available rather
    # than stating an actual year cutoff (e.g. "the oldest I have", "my
    # newest gear") -- a *relative* preference the deterministic scorer
    # (pipeline/recommend.py) can act on, unlike released_no_later_than/
    # released_no_earlier_than, which need an absolute year the LLM can't invent
    # just because the user said "oldest". Mutually exclusive in practice,
    # not enforced as such.
    prefer_oldest: bool = False
    prefer_newest: bool = False
    # Set when the user asks for a build that's no more powerful than
    # necessary (e.g. "but not more powerful than that") -- the deterministic
    # scorer (pipeline/recommend.py) then prefers the build that's just
    # sufficient for the stated goal over the most capable one available,
    # and the ranking LLM is instructed (llm/prompts.py) to do the same.
    prefer_minimal_spec: bool = False
    # Set when the user wants the single most capable GPU available rather
    # than stating a concrete VRAM target (e.g. "the biggest model my
    # hardware can run", "the best GPU I have") -- a *relative* preference
    # like prefer_oldest/prefer_newest, for the same reason: the LLM can't
    # invent a min_vram_gb number for "biggest available" without knowing
    # what's actually in the inventory. Without this, a build with any GPU
    # always has a (deliberately gentle) power-draw score penalty and
    # nothing to offset it unless a concrete min_vram_gb happened to be
    # inferred, so a GPU-less build would quietly win by default even when
    # the user clearly wants a capable GPU.
    prefer_max_vram: bool = False
    # Set by the LLM when the conversation so far is too vague to confidently
    # fill in the fields above (e.g. no hint of budget/power constraints,
    # intended use, or whether a display output is needed) -- surfaced to
    # the user as part of the assistant's chat reply (pipeline/recommend.py)
    # instead of silently guessing. Left null once enough is known.
    clarifying_question: str | None = None
    notes: str = ""


def fallback_requirements(user_prompt: str) -> ProjectRequirements:
    """Conservative defaults used when the LLM's output never validates
    (SPEC.md §5 step 1: fall back to conservative defaults + a warning)."""
    return ProjectRequirements(
        use_case=user_prompt,
        notes="LLM interpretation of the project description failed; using conservative defaults.",
    )
