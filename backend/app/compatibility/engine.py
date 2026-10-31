"""Combines candidates into builds and keeps only those where every rule is
pass or unknown (SPEC.md §5 step 3). No LLM involved: candidates are assumed
already filtered (quantity > 0, condition != faulty, any hard requirements)
by the caller — that filtering is the pipeline's job (Phase 3).

Combinatorics are bounded by `top_n` per category (SPEC.md §6: "bound the
combinatorics ... so it runs quickly with ~200 components"). Candidates
are taken in the order given — ranking candidates by relevance before
calling the engine is the caller's responsibility.
"""

from app.compatibility.rules import ALL_RULES, display_output_available
from app.compatibility.types import Build, BuildEvaluation, CandidateComponent, EngineResult, RuleResult
from app.enums import Category

REQUIRED_CATEGORIES = [
    Category.CPU,
    Category.MOTHERBOARD,
    Category.RAM,
    Category.STORAGE,
    Category.PSU,
    Category.CASE,
    Category.COOLER,
]


def evaluate_build(build: Build, *, headless: bool = False) -> dict[str, RuleResult]:
    results = {rule.__name__: rule(build) for rule in ALL_RULES}
    results["display_output_available"] = display_output_available(build, headless=headless)
    return results


def is_build_valid(rule_results: dict[str, RuleResult]) -> bool:
    return all(result.status != "fail" for result in rule_results.values())


def generate_builds(
    candidates: dict[Category, list[CandidateComponent]],
    *,
    headless: bool = False,
    top_n: int = 5,
) -> EngineResult:
    missing = [category for category in REQUIRED_CATEGORIES if not candidates.get(category)]
    if missing:
        return EngineResult(builds=[], missing=missing)

    def top(category: Category) -> list[CandidateComponent]:
        return candidates.get(category, [])[:top_n]

    gpu_options: list[CandidateComponent | None] = [None, *top(Category.GPU)]

    builds: list[BuildEvaluation] = []
    for cpu in top(Category.CPU):
        for motherboard in top(Category.MOTHERBOARD):
            for ram in top(Category.RAM):
                for storage in top(Category.STORAGE):
                    for psu in top(Category.PSU):
                        for case in top(Category.CASE):
                            for cooler in top(Category.COOLER):
                                for gpu in gpu_options:
                                    build = Build(
                                        cpu=cpu,
                                        motherboard=motherboard,
                                        ram=ram,
                                        storage=storage,
                                        psu=psu,
                                        case=case,
                                        cooler=cooler,
                                        gpu=gpu,
                                    )
                                    rule_results = evaluate_build(build, headless=headless)
                                    if is_build_valid(rule_results):
                                        builds.append(BuildEvaluation(build=build, rule_results=rule_results))

    return EngineResult(builds=builds, missing=[])
