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


def interpret_requirements(
    user_prompt: str, llm_client: LLMClient
) -> tuple[ProjectRequirements, LlmCallStatus]:
    return call_llm_with_retry(
        llm_client,
        system=REQUIREMENTS_SYSTEM_PROMPT,
        build_prompt=lambda error: build_requirements_prompt(user_prompt, error_feedback=error),
        schema=ProjectRequirements,
        fallback=fallback_requirements(user_prompt),
    )


def _meets_hard_requirements(category: Category, specs, requirements: ProjectRequirements) -> bool:
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
    return True


def prefilter_candidates(
    db: Session, requirements: ProjectRequirements
) -> dict[Category, list[CandidateComponent]]:
    candidates: dict[Category, list[CandidateComponent]] = {}
    rows = db.query(Component).filter(Component.quantity > 0, Component.condition != Condition.FAULTY).all()
    for row in rows:
        specs = ComponentSpecsAdapter.validate_python(row.specs)
        if not _meets_hard_requirements(row.category, specs, requirements):
            continue
        candidates.setdefault(row.category, []).append(
            CandidateComponent(id=row.id, name=row.name, specs=specs)
        )
    return candidates


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
            "motherboard": evaluation.build.motherboard.name,
            "ram": evaluation.build.ram.name,
            "gpu": evaluation.build.gpu.name if evaluation.build.gpu else None,
            "warnings": evaluation.warnings,
        }
        for idx, evaluation in enumerate(pool)
    ]
    known_ids = {summary["build_id"] for summary in summaries}

    def validate(ranking: BuildRanking) -> None:
        for entry in ranking.ranking:
            if entry.build_id not in known_ids:
                raise ValueError(f"Invented build_id: {entry.build_id}")

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
        ComponentSummary(id=c.id, category=Category(c.specs.category), name=c.name)
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
        components.append(ComponentSummary(id=build.gpu.id, category=Category.GPU, name=build.gpu.name))

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
        "cpu": {"name": build.cpu.name, "cores": build.cpu.specs.cores, "threads": build.cpu.specs.threads},
        "gpu": {"name": build.gpu.name, "vram_gb": build.gpu.specs.vram_gb} if build.gpu else None,
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


def recommend(*, prompt: str, max_builds: int, db: Session, llm_client: LLMClient) -> RecommendResponse:
    settings = get_settings()

    requirements, interpret_status = interpret_requirements(prompt, llm_client)

    candidates = prefilter_candidates(db, requirements)
    forced_missing: list[Category] = []
    if requirements.min_vram_gb is not None and not candidates.get(Category.GPU):
        forced_missing.append(Category.GPU)

    engine_result = generate_builds(
        candidates, headless=requirements.headless, top_n=settings.recommend_top_n
    )
    missing = list(dict.fromkeys([*engine_result.missing, *forced_missing]))

    evaluations = engine_result.builds
    if requirements.min_vram_gb is not None:
        evaluations = [e for e in evaluations if e.build.gpu is not None]

    if not evaluations:
        reply, reply_status = generate_chat_reply(prompt, requirements, [], [], missing, llm_client)
        return RecommendResponse(
            builds=[],
            missing=missing,
            llm_used=LlmUsed(interpret=interpret_status, rank="ok", reply=reply_status),
            assistant_message=reply,
        )

    pool_size = max(max_builds * 3, 10)
    pool = sorted(evaluations, key=lambda e: deterministic_score(e, requirements), reverse=True)[:pool_size]

    ranked, rank_status = rank_builds(pool, requirements, llm_client)
    reason_by_index = dict(ranked)

    ordered_indices = [idx for idx, _ in ranked]
    remaining_indices = sorted(
        (i for i in range(len(pool)) if i not in reason_by_index),
        key=lambda i: deterministic_score(pool[i], requirements),
        reverse=True,
    )
    final_indices = (ordered_indices + remaining_indices)[:max_builds]

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
