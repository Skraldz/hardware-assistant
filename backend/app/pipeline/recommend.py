"""Orchestrates the recommend pipeline (SPEC.md §5, extended with a chat
reply step):

1. Interpret the free-text prompt into ProjectRequirements (LLM).
2. Deterministically prefilter inventory (quantity>0, not faulty, hard
   minimums from step 1).
3. Generate verified-compatible builds (compatibility engine, Phase 2).
4. Rank the builds by fit to the requirements (LLM), rejecting any
   hallucinated build_id.
5. Re-verify the chosen builds (defense in depth).
6. Write a conversational reply to the user's latest message (LLM), using
   the already-computed builds as context -- so a genuine question ("what
   model can I run on these?") gets answered instead of only ever
   restating that builds were found.

No agentic tool-calling: this is a fixed sequence of plain function calls.
"""

import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.compatibility.engine import evaluate_build, generate_builds
from app.compatibility.types import BuildEvaluation, CandidateComponent
from app.config import get_settings
from app.enums import Category, Condition
from app.llm.client import LLMClient
from app.llm.parsing import LlmCallStatus, call_llm_with_retry
from app.llm.prompts import (
    CHAT_REPLY_SYSTEM_PROMPT,
    RANKING_SYSTEM_PROMPT,
    REQUIREMENTS_SYSTEM_PROMPT,
    build_chat_reply_prompt,
    build_ranking_prompt,
    build_requirements_prompt,
)
from app.models import Component
from app.schemas.builds import (
    BuildRanking,
    BuildResult,
    ChatReply,
    ComponentSummary,
    LlmUsed,
    RecommendResponse,
    RuleResultOut,
)
from app.schemas.components import ComponentSpecsAdapter
from app.schemas.requirements import ProjectRequirements, fallback_requirements

logger = logging.getLogger(__name__)


def _validate_requirements(requirements: ProjectRequirements) -> None:
    """Semantic check the JSON schema cannot express, run through the same
    retry-with-feedback path as a hallucinated build_id.

    The era bounds are the one place this model reliably gets a *direction*
    wrong. Measured against qwen2.5:7b-instruct over eight phrasings: the
    original `max_release_year`/`min_release_year` pair was read backwards
    often enough to score 3/6 -- "from 2010 or earlier" became
    `min_release_year=2010`, which both admitted newer hardware and excluded
    the genuinely old parts the user asked for. Renaming the fields to say
    their own direction and giving two worked examples took that to 6/8, but
    6/8 is not reliability, and an inverted era bound is worse than a missing
    one: the user gets a confident answer built from the opposite of what
    they asked for.

    An upper bound ("nothing newer than X") alongside prefer_newest, or a
    lower bound alongside prefer_oldest, is self-contradictory in the
    direction this specific failure produces, so it is rejected and the model
    gets one attempt to correct itself with the reason fed back. If it
    insists, the conservative fallback applies and the era constraint is
    dropped entirely -- losing a requirement is recoverable (the user can
    rephrase), silently inverting one is not.

    Note this deliberately does not try to repair the value by flipping it.
    "The oldest parts I have, but nothing before 2010" is a coherent request
    that produces the same field combination, and guessing which of the two
    the user meant would be the same class of mistake the model just made.
    """
    if requirements.prefer_oldest and requirements.released_no_earlier_than is not None:
        raise ValueError(
            "prefer_oldest is set together with released_no_earlier_than="
            f"{requirements.released_no_earlier_than}, which excludes the oldest hardware. "
            "If the user asked for hardware from a year or earlier, that is "
            "released_no_later_than. Re-read which field means which direction."
        )
    if requirements.prefer_newest and requirements.released_no_later_than is not None:
        raise ValueError(
            "prefer_newest is set together with released_no_later_than="
            f"{requirements.released_no_later_than}, which excludes the newest hardware. "
            "If the user asked for hardware from a year or newer, that is "
            "released_no_earlier_than. Re-read which field means which direction."
        )


def interpret_requirements(
    user_prompt: str, llm_client: LLMClient
) -> tuple[ProjectRequirements, LlmCallStatus]:
    return call_llm_with_retry(
        llm_client,
        system=REQUIREMENTS_SYSTEM_PROMPT,
        build_prompt=lambda error: build_requirements_prompt(user_prompt, error_feedback=error),
        schema=ProjectRequirements,
        fallback=fallback_requirements(user_prompt),
        validate=_validate_requirements,
    )


def _meets_hard_requirements(
    category: Category, release_year: int | None, specs, requirements: ProjectRequirements
) -> bool:
    """SPEC.md §5 step 2: drop candidates that don't provably meet a hard
    minimum. Missing data counts as "doesn't meet it" here — unlike the
    compatibility rules (Phase 2), a hard requirement the user actually
    asked for shouldn't be satisfied by a guess."""
    if category == Category.GPU and requirements.min_vram_gb is not None:
        if specs.vram_gb is None or specs.vram_gb < requirements.min_vram_gb:
            return False
    if category == Category.RAM and requirements.min_ram_gb is not None:
        if specs.capacity_gb_per_module is None or specs.modules is None:
            return False
        if specs.capacity_gb_per_module * specs.modules < requirements.min_ram_gb:
            return False
    if category == Category.STORAGE and requirements.min_storage_gb is not None:
        if specs.capacity_gb is None or specs.capacity_gb < requirements.min_storage_gb:
            return False
    if category == Category.CPU and requirements.min_cpu_cores is not None:
        if specs.cores is None or specs.cores < requirements.min_cpu_cores:
            return False
    # release_year applies to every category alike (it's metadata about the
    # part, not a capability), unlike the checks above.
    if requirements.released_no_later_than is not None:
        if release_year is None or release_year > requirements.released_no_later_than:
            return False
    if requirements.released_no_earlier_than is not None:
        if release_year is None or release_year < requirements.released_no_earlier_than:
            return False
    return True


def _gpu_is_required(requirements: ProjectRequirements) -> bool:
    """Whether a build must include a discrete GPU to be offered at all.

    A discrete GPU is the only component a valid build can legitimately omit
    (engine.REQUIRED_CATEGORIES covers the other seven, and a build missing
    any of those is never generated), so it's the only category
    `required_categories` can actually constrain -- but it does need to
    constrain it. `min_vram_gb` already forced a GPU; `required_categories`
    was parsed into ProjectRequirements and then never read, so a user who
    asked for a graphics card without naming a VRAM figure got a silently
    ignored requirement. Worse than ignored in practice: deterministic_score
    penalises the GPU's TDP with its always-on power-draw nudge, with
    nothing opposing it unless prefer_max_vram happens to be set, so the
    GPU-less build actively won.
    """
    return requirements.min_vram_gb is not None or Category.GPU in requirements.required_categories


def _era_rank(release_year: int | None, requirements: ProjectRequirements) -> int:
    """Lower sorts first. Era only breaks ties when the user actually
    expressed a direction (prefer_oldest/prefer_newest) -- with neither set,
    every component ranks equally here, so this step never biases ordering
    toward "newest" by default. A component with no known release_year
    sorts last in either direction, rather than winning by omission."""
    if requirements.prefer_oldest:
        return release_year if release_year is not None else 10**9
    if requirements.prefer_newest:
        return -release_year if release_year is not None else 0
    return 0


def _overshoot_rank(category: Category, specs, requirements: ProjectRequirements) -> float:
    """Lower sorts first: how far a single component overshoots the
    smallest stated hard minimum for its category, if any was given.
    Mirrors deterministic_score's own overshoot logic, but per-component
    rather than per-build, since this runs before any build exists."""
    if category == Category.GPU:
        if requirements.prefer_max_vram:
            # Opposite direction from the overshoot logic below: "the
            # biggest GPU available" has no minimum to measure overshoot
            # against, it just wants the largest vram_gb first.
            return -(specs.vram_gb or 0)
        if requirements.min_vram_gb is not None:
            return max((specs.vram_gb or 0) - requirements.min_vram_gb, 0)
    if category == Category.CPU and requirements.min_cpu_cores is not None:
        return max((specs.cores or 0) - requirements.min_cpu_cores, 0)
    if category == Category.RAM and requirements.min_ram_gb is not None:
        capacity = (specs.capacity_gb_per_module or 0) * (specs.modules or 0)
        return max(capacity - requirements.min_ram_gb, 0)
    if category == Category.STORAGE:
        if requirements.min_storage_gb is not None:
            return max((specs.capacity_gb or 0) - requirements.min_storage_gb, 0)
        # No stated minimum: default to preferring more capacity, the same
        # direction deterministic_score's own gentle capacity nudge already
        # takes. Without this, the top-N storage candidates (and therefore
        # the pool `_storage_combos`/MAX_STORAGE_PAIR_CANDIDATES draws
        # 2-drive pairs from) were whichever drives happened to have the
        # lowest database id, not the biggest ones -- a 2-drive combo could
        # never actually win on total capacity if it was never built from
        # the inventory's largest drives in the first place.
        return -(specs.capacity_gb or 0)
    return 0


def _sort_candidates_by_relevance(
    candidates: dict[Category, list[CandidateComponent]],
    requirements: ProjectRequirements,
    *,
    top_n_hint: int,
) -> dict[Category, list[CandidateComponent]]:
    """The compatibility engine (engine.py) only ever looks at the first
    `top_n` candidates per category, in whatever order it receives them --
    by its own design, sorting by relevance before calling it is the
    caller's job (its module docstring says so explicitly). Without this,
    `top_n` just keeps whichever rows a plain, unordered database query
    happens to return first (effectively insertion order in practice),
    which permanently hid the rest of a large inventory from every
    recommendation regardless of what was actually asked for -- the root
    cause of a real live-deployment bug (docs/ai-log.md) where every build
    kept using the same handful of components no matter the prompt.
    `id` is the final, stable tiebreaker so results stay reproducible.

    `top_n_hint` should match whatever top_n the compatibility engine will
    actually use (settings.recommend_top_n) -- used below only to decide
    how many motherboard/CPU candidates count as "the ones that will
    actually be tried", for the cross-category checks that follow.
    """
    ranked = {
        category: sorted(
            items,
            key=lambda c: (
                _era_rank(c.release_year, requirements),
                _overshoot_rank(category, c.specs, requirements),
                c.id,
            ),
        )
        for category, items in candidates.items()
    }

    # cpu_socket_matches_board (rules.py) is a strict, no-exceptions match --
    # unlike case/cooler fit, which is usually forgiving (an ATX case fits
    # mATX too; most coolers list several sockets), a CPU and motherboard
    # either share a socket or can never be paired at all. Sorting CPU
    # candidates purely by overshoot/era, independently of which sockets
    # the top motherboards actually have, let several same-overshoot CPUs
    # from older, incompatible sockets crowd out the one CPU that would
    # have actually paired with something -- the real cause of a live
    # "no compatible builds" report despite a proven-compatible combination
    # existing elsewhere in the inventory (docs/ai-log.md has the full
    # trace: ten historical CPUs tied at "exactly meets min_cpu_cores"
    # spanned six different sockets, none of which matched any of the
    # independently-ranked top motherboards). Re-rank CPU to prefer a
    # socket among the top motherboards, ahead of (not instead of) the
    # existing overshoot/era preference.
    motherboards = ranked.get(Category.MOTHERBOARD, [])[:top_n_hint]
    board_sockets = {m.specs.socket for m in motherboards if m.specs.socket}
    if board_sockets and Category.CPU in ranked:
        ranked[Category.CPU] = sorted(
            ranked[Category.CPU],
            key=lambda c: (
                c.specs.socket is not None and c.specs.socket not in board_sockets,
                _era_rank(c.release_year, requirements),
                _overshoot_rank(Category.CPU, c.specs, requirements),
                c.id,
            ),
        )

    # Same failure mode, same fix: ram_type_matches (rules.py) needs the
    # RAM's single memory_type to appear in both the motherboard's and the
    # CPU's supported lists -- also a strict, no-exceptions match.
    cpus = ranked.get(Category.CPU, [])[:top_n_hint]
    cpu_mem_types = {t for c in cpus if c.specs.memory_type for t in c.specs.memory_type}
    board_mem_types = {t for m in motherboards if m.specs.memory_type for t in m.specs.memory_type}
    allowed_mem_types = (cpu_mem_types & board_mem_types) or cpu_mem_types or board_mem_types
    if allowed_mem_types and Category.RAM in ranked:
        ranked[Category.RAM] = sorted(
            ranked[Category.RAM],
            key=lambda c: (
                c.specs.memory_type is not None and c.specs.memory_type not in allowed_mem_types,
                _era_rank(c.release_year, requirements),
                _overshoot_rank(Category.RAM, c.specs, requirements),
                c.id,
            ),
        )

    return ranked


def prefilter_candidates(
    db: Session, requirements: ProjectRequirements, *, top_n_hint: int = 5
) -> dict[Category, list[CandidateComponent]]:
    candidates: dict[Category, list[CandidateComponent]] = {}
    rows = db.query(Component).filter(Component.quantity > 0, Component.condition != Condition.FAULTY).all()
    for row in rows:
        try:
            specs = ComponentSpecsAdapter.validate_python(row.specs)
        except ValidationError:
            # One row whose stored specs JSON no longer satisfies its spec
            # class (a hand-edited row, a category changed out of band, a
            # literal removed from the schema) must not take down every
            # recommendation. Skip it and log it: a degraded result beats a
            # 500 on an endpoint whose whole job is "work with what's there".
            logger.warning(
                "Skipping component %s (%r): stored specs are not valid for category %s",
                row.id,
                row.name,
                row.category,
            )
            continue
        if not _meets_hard_requirements(row.category, row.release_year, specs, requirements):
            continue
        candidates.setdefault(row.category, []).append(
            CandidateComponent(id=row.id, name=row.name, specs=specs, release_year=row.release_year)
        )
    return _sort_candidates_by_relevance(candidates, requirements, top_n_hint=top_n_hint)


def deterministic_score(evaluation: BuildEvaluation, requirements: ProjectRequirements) -> float:
    """Fallback ranking when the LLM's output is unusable, and the
    pre-ranking used to bound how many builds get sent to the LLM. Also
    shown to the user as each build's "score" (RecommendView.jsx's guide
    panel explains what it means) -- when the LLM ranking succeeds, this
    score is still displayed, but the actual order and each build's
    `reason` come from the LLM, not from this value.

    Every preference below has two forms: a strong deduction when the
    matching ProjectRequirements flag is explicitly set (unchanged from
    before, and exactly what the existing prefer_* tests assert), and a
    much gentler always-on nudge in the same direction otherwise -- so
    builds aren't uniformly stuck at 100 just because nothing was
    explicitly requested, while an explicit preference still dominates.
    """
    score = 100.0
    score -= 5 * len(evaluation.warnings)

    total_tdp = evaluation.build.cpu.specs.tdp_w or 0
    if evaluation.build.gpu is not None:
        total_tdp += evaluation.build.gpu.specs.tdp_w or 0
    if requirements.prefer_low_power:
        score -= total_tdp * 0.05
    else:
        score -= total_tdp * 0.01

    if requirements.prefer_max_vram:
        # Without this, a build with any GPU always has a strictly higher
        # total_tdp than the same build without one, so the gentle
        # power-draw nudge above would always favor "no GPU" by default --
        # exactly backwards for a request like "the biggest model my
        # hardware can run". A GPU-less build gets 0 here; any GPU clearly
        # outweighs the few points the TDP nudge could have cost it, and
        # a bigger GPU keeps winning over a smaller one.
        gpu_vram = evaluation.build.gpu.specs.vram_gb if evaluation.build.gpu else 0
        score += (gpu_vram or 0) * 3

    # A gentle, always-on nudge toward more total storage capacity -- without
    # it, this score has no opinion on storage at all, so a 1-drive and an
    # otherwise-identical 2-drive build tie exactly. `_storage_combos`
    # (engine.py) always lists every 1-drive option before any 2-drive one,
    # so a tie's stable sort order then permanently buried every multi-drive
    # build behind the (often far more numerous) tied 1-drive builds once
    # the ranking pool got truncated to pool_size -- multi-drive builds were
    # engine-valid but could never actually surface to a user. 0.001/GB is
    # deliberately tiny (an extra 1TB drive is worth ~1 point) -- just
    # enough to break this specific tie in favor of more capacity, not
    # enough to meaningfully outweigh any other factor above.
    total_storage_gb = sum(s.specs.capacity_gb or 0 for s in evaluation.build.storage)
    score += total_storage_gb * 0.001

    size_rank = {"ITX": 0, "mATX": 1, "ATX": 2, "EATX": 3}
    supported = evaluation.build.case.specs.supported_form_factors
    smallest_supported = min((size_rank.get(f, 2) for f in supported), default=2) if supported else None
    if smallest_supported is not None:
        if requirements.prefer_small_form_factor:
            score -= smallest_supported * 5
        else:
            score -= smallest_supported * 1

    if requirements.prefer_minimal_spec:
        # Prefer the build that's just sufficient for the stated goal, not
        # the most capable hardware available -- penalise capability beyond
        # whatever minimum was inferred (or any capability at all, if no
        # minimum was given).
        gpu_vram = evaluation.build.gpu.specs.vram_gb if evaluation.build.gpu else 0
        vram_over = max((gpu_vram or 0) - (requirements.min_vram_gb or 0), 0)
        score -= vram_over * 2

        cpu_cores = evaluation.build.cpu.specs.cores or 0
        cores_over = max(cpu_cores - (requirements.min_cpu_cores or 0), 0)
        score -= cores_over * 2
    else:
        # Only nudge against overshoot when a real minimum was actually
        # stated -- without one, there's no baseline to call anything
        # "more than necessary", so a build is never penalised just for
        # having a GPU or a many-core CPU when nothing asked for either.
        if requirements.min_vram_gb is not None:
            gpu_vram = evaluation.build.gpu.specs.vram_gb if evaluation.build.gpu else 0
            vram_over = max((gpu_vram or 0) - requirements.min_vram_gb, 0)
            score -= vram_over * 0.3
        if requirements.min_cpu_cores is not None:
            cpu_cores = evaluation.build.cpu.specs.cores or 0
            cores_over = max(cpu_cores - requirements.min_cpu_cores, 0)
            score -= cores_over * 0.3

    if requirements.prefer_oldest or requirements.prefer_newest:
        # A build is only as modern as its newest core component -- an
        # otherwise-vintage build paired with one recent part still isn't
        # "old", so the latest year among cpu/motherboard/ram/gpu stands in
        # for the whole build's era (missing years are ignored rather than
        # treated as 0, which would otherwise make an unlabeled part look
        # maximally "old" and dominate the comparison).
        core_components = [
            evaluation.build.cpu,
            evaluation.build.motherboard,
            evaluation.build.ram,
            evaluation.build.gpu,
        ]
        years = [c.release_year for c in core_components if c is not None and c.release_year is not None]
        if years:
            build_year = max(years)
            if requirements.prefer_oldest:
                score -= (build_year - 2000) * 0.5
            else:
                score -= (2030 - build_year) * 0.5

    return score


def rank_builds(
    pool: list[BuildEvaluation],
    requirements: ProjectRequirements,
    llm_client: LLMClient,
) -> tuple[list[tuple[int, str]], LlmCallStatus]:
    """Returns an ordered list of (pool_index, reason) — the LLM's preferred
    order, restricted to ids it was actually offered. Empty on fallback."""
    if not pool:
        return [], "ok"

    summaries = [
        {
            "build_id": idx,
            "cpu": evaluation.build.cpu.name,
            "cpu_release_year": evaluation.build.cpu.release_year,
            "motherboard": evaluation.build.motherboard.name,
            "ram": evaluation.build.ram.name,
            "gpu": evaluation.build.gpu.name if evaluation.build.gpu else None,
            "gpu_vram_gb": evaluation.build.gpu.specs.vram_gb if evaluation.build.gpu else None,
            "gpu_release_year": evaluation.build.gpu.release_year if evaluation.build.gpu else None,
            "warnings": evaluation.warnings,
        }
        for idx, evaluation in enumerate(pool)
    ]
    known_ids = {summary["build_id"] for summary in summaries}

    def validate(ranking: BuildRanking) -> None:
        seen: set[int] = set()
        for entry in ranking.ranking:
            if entry.build_id not in known_ids:
                raise ValueError(f"Invented build_id: {entry.build_id}")
            # A repeated id isn't invented, but it would show the user the
            # same build twice (and make _select_diverse_builds treat the
            # second copy as a CPU repeat), so it's rejected the same way.
            if entry.build_id in seen:
                raise ValueError(f"Duplicate build_id: {entry.build_id}")
            seen.add(entry.build_id)

    ranking, status = call_llm_with_retry(
        llm_client,
        system=RANKING_SYSTEM_PROMPT,
        build_prompt=lambda error: build_ranking_prompt(summaries, requirements, error_feedback=error),
        schema=BuildRanking,
        fallback=BuildRanking(ranking=[]),
        validate=validate,
    )
    return [(entry.build_id, entry.reason) for entry in ranking.ranking], status


def _to_build_result(
    evaluation: BuildEvaluation,
    *,
    reason: str,
    score: float,
    headless: bool,
) -> BuildResult:
    build = evaluation.build
    components = [
        ComponentSummary(
            id=c.id, category=Category(c.specs.category), name=c.name, release_year=c.release_year
        )
        for c in (
            build.cpu,
            build.motherboard,
            build.ram,
            *build.storage,
            build.psu,
            build.case,
            build.cooler,
        )
    ]
    if build.gpu is not None:
        components.append(
            ComponentSummary(
                id=build.gpu.id,
                category=Category.GPU,
                name=build.gpu.name,
                release_year=build.gpu.release_year,
            )
        )

    # Final verification (SPEC.md §5 step 5, defense in depth): re-run the
    # rules on the chosen build rather than trusting the earlier pass.
    verified = evaluate_build(build, headless=headless)
    rule_results = {name: RuleResultOut(status=r.status, message=r.message) for name, r in verified.items()}
    return BuildResult(
        components=components,
        rule_results=rule_results,
        warnings=[r.message for r in verified.values() if r.status == "unknown"],
        reason=reason,
        score=score,
    )


def _fallback_message(
    builds: list[BuildResult], missing: list[Category], requirements: ProjectRequirements
) -> str:
    """A short, deterministic natural-language summary of the result, used
    as generate_chat_reply()'s fallback when the chat-reply LLM call is
    unavailable or never returns valid JSON -- the result (and the
    clarifying question, if the requirements-interpretation LLM asked for
    one) is already fully determined by the structured data above, so a
    reasonable message can always be produced without an LLM."""
    missing_note = (
        f" No compatible options were found for: {', '.join(c.value for c in missing)}." if missing else ""
    )
    question_note = f" {requirements.clarifying_question}" if requirements.clarifying_question else ""

    if not builds:
        result = "I couldn't put together a compatible build from the current inventory." + missing_note
    else:
        lead = f"Found {len(builds)} compatible build{'s' if len(builds) != 1 else ''}."
        result = f"{lead} Top pick: {builds[0].reason}{missing_note}"
    return result + question_note


def _chat_build_summary(index: int, build_result: BuildResult, evaluation: BuildEvaluation) -> dict:
    """A build summary for the chat-reply prompt that includes actual specs
    (not just component names), so the LLM can ground a comment like "this
    GPU's 6GB VRAM comfortably exceeds Crysis's minimum" in real numbers
    instead of guessing them from a product name."""
    build = evaluation.build
    ram_gb = None
    if build.ram.specs.capacity_gb_per_module and build.ram.specs.modules:
        ram_gb = build.ram.specs.capacity_gb_per_module * build.ram.specs.modules
    return {
        "build": index + 1,
        "cpu": {
            "name": build.cpu.name,
            "cores": build.cpu.specs.cores,
            "threads": build.cpu.specs.threads,
            "release_year": build.cpu.release_year,
        },
        "gpu": {
            "name": build.gpu.name,
            "vram_gb": build.gpu.specs.vram_gb,
            "release_year": build.gpu.release_year,
        }
        if build.gpu
        else None,
        "ram_gb": ram_gb,
        "storage": [
            {"name": drive.name, "interface": drive.specs.interface, "capacity_gb": drive.specs.capacity_gb}
            for drive in build.storage
        ],
        "reason": build_result.reason,
        "warnings": build_result.warnings,
    }


def generate_chat_reply(
    prompt: str,
    requirements: ProjectRequirements,
    builds: list[BuildResult],
    evaluations: list[BuildEvaluation],
    missing: list[Category],
    llm_client: LLMClient,
) -> tuple[str, LlmCallStatus]:
    """Writes the assistant's reply to the user's latest message (the last
    line of `prompt`, the flattened conversation transcript), using the
    already-computed builds (with their actual specs, via `evaluations`,
    parallel to `builds`) as context -- so a genuine question ("what model
    can I run on these?") gets an actual answer, not just a restated build
    summary. Falls back to a deterministic summary (_fallback_message) if
    the LLM is unavailable or never returns valid JSON."""
    build_summaries = [
        _chat_build_summary(idx, build, evaluation)
        for idx, (build, evaluation) in enumerate(zip(builds, evaluations, strict=True))
    ]
    reply, status = call_llm_with_retry(
        llm_client,
        system=CHAT_REPLY_SYSTEM_PROMPT,
        build_prompt=lambda error: build_chat_reply_prompt(
            prompt, build_summaries, [c.value for c in missing], error_feedback=error
        ),
        schema=ChatReply,
        fallback=ChatReply(reply=_fallback_message(builds, missing, requirements)),
    )
    return reply.reply, status


def _select_diverse_builds(
    ranked_order: list[int], pool: list[BuildEvaluation], max_builds: int
) -> list[int]:
    """Picks up to max_builds indices from ranked_order (already best-first,
    whether by deterministic score, the LLM's ranking, or the deterministic
    fallback), actively preferring builds that don't repeat an already-chosen
    CPU or GPU.

    Without this, the top few results tend to differ only in whichever
    category had the least decisive "best" pick (e.g. storage or cooler):
    sorting candidates by relevance before the engine's top_n cutoff
    (_sort_candidates_by_relevance) means a single best CPU/motherboard/RAM
    combination legitimately dominates the top of the ranking, so the
    highest-scoring builds were all minor variations of it. Falls back to
    repeating a CPU/GPU once there aren't enough distinct options left in
    the pool, so this never returns fewer builds than the caller asked for
    just because the inventory lacks variety.

    Used twice in recommend(): once to choose the pool offered to the ranking
    LLM, and once on the order that comes back. Both passes are needed -- the
    first so the LLM has genuinely different builds to rank at all, the second
    so its chosen order doesn't re-collapse onto one CPU."""
    remaining = list(ranked_order)
    selected: list[int] = []
    used_cpu_ids: set[int] = set()
    used_gpu_ids: set[int] = set()

    def diversity_key(idx: int) -> tuple[bool, bool]:
        # CPU takes priority over GPU: a tuple sorts on its first element
        # first, so a not-yet-used CPU always outranks a not-yet-used GPU
        # alone. GPU only decides between two builds that are tied on
        # CPU-repeat status (most often: no CPU variety left at all).
        build = pool[idx].build
        cpu_repeat = build.cpu.id in used_cpu_ids
        gpu_repeat = build.gpu is not None and build.gpu.id in used_gpu_ids
        return (cpu_repeat, gpu_repeat)

    while remaining and len(selected) < max_builds:
        remaining.sort(key=diversity_key)  # stable: preserves rank order within each group
        idx = remaining.pop(0)
        selected.append(idx)
        used_cpu_ids.add(pool[idx].build.cpu.id)
        if pool[idx].build.gpu is not None:
            used_gpu_ids.add(pool[idx].build.gpu.id)

    return selected


def recommend(*, prompt: str, max_builds: int, db: Session, llm_client: LLMClient) -> RecommendResponse:
    settings = get_settings()

    requirements, interpret_status = interpret_requirements(prompt, llm_client)

    candidates = prefilter_candidates(db, requirements, top_n_hint=settings.recommend_top_n)
    # A category the user explicitly required but has no (surviving) candidate
    # for is reported by name, rather than letting the build simply come back
    # without it. For the seven categories in engine.REQUIRED_CATEGORIES the
    # engine already reports this; this covers GPU, which the engine treats
    # as optional, and keeps reporting honest if required_categories ever
    # names something whose candidates were all dropped by
    # _meets_hard_requirements.
    forced_missing = [c for c in requirements.required_categories if not candidates.get(c)]
    if _gpu_is_required(requirements) and not candidates.get(Category.GPU):
        forced_missing.append(Category.GPU)

    engine_result = generate_builds(
        candidates, headless=requirements.headless, top_n=settings.recommend_top_n
    )
    missing = list(dict.fromkeys([*engine_result.missing, *forced_missing]))

    evaluations = engine_result.builds
    if _gpu_is_required(requirements):
        evaluations = [e for e in evaluations if e.build.gpu is not None]

    if not evaluations:
        reply, reply_status = generate_chat_reply(prompt, requirements, [], [], missing, llm_client)
        return RecommendResponse(
            builds=[],
            missing=missing,
            llm_used=LlmUsed(interpret=interpret_status, rank="ok", reply=reply_status),
            assistant_message=reply,
        )

    # The pool bounds how many builds get sent to the ranking LLM. Picking it
    # by deterministic score *alone* was the second half of the "all three
    # suggestions are basically the same" bug: whenever one CPU scored best,
    # every one of its many variations (different storage/cooler/PSU) outranked
    # every build using any other CPU, so the pool was filled with a single
    # CPU and the diversity step below had nothing left to diversify over --
    # it fell back to repeats, as designed, on a pool that should never have
    # been homogeneous. Selecting the pool with the same diversity-aware
    # greedy means the ranking LLM is offered genuinely different builds, and
    # _select_diverse_builds still runs afterwards as a guard on the order the
    # LLM actually returns. The highest-scoring build is still picked first in
    # both passes, so the top recommendation is unchanged.
    pool_size = max(max_builds * 3, 10)
    by_score = sorted(
        range(len(evaluations)),
        key=lambda i: deterministic_score(evaluations[i], requirements),
        reverse=True,
    )
    pool = [evaluations[i] for i in _select_diverse_builds(by_score, evaluations, pool_size)]

    ranked, rank_status = rank_builds(pool, requirements, llm_client)
    reason_by_index = dict(ranked)

    ordered_indices = [idx for idx, _ in ranked]
    remaining_indices = sorted(
        (i for i in range(len(pool)) if i not in reason_by_index),
        key=lambda i: deterministic_score(pool[i], requirements),
        reverse=True,
    )
    final_indices = _select_diverse_builds(ordered_indices + remaining_indices, pool, max_builds)

    builds = [
        _to_build_result(
            pool[idx],
            reason=reason_by_index.get(
                idx, f"Automatically selected (score {deterministic_score(pool[idx], requirements):.0f})."
            ),
            score=deterministic_score(pool[idx], requirements),
            headless=requirements.headless,
        )
        for idx in final_indices
    ]

    chosen_evaluations = [pool[idx] for idx in final_indices]
    reply, reply_status = generate_chat_reply(
        prompt, requirements, builds, chosen_evaluations, missing, llm_client
    )
    return RecommendResponse(
        builds=builds,
        missing=missing,
        llm_used=LlmUsed(interpret=interpret_status, rank=rank_status, reply=reply_status),
        assistant_message=reply,
    )
