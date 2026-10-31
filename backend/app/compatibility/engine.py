"""Combines candidates into builds and keeps only those where every rule is
pass or unknown (SPEC.md §5 step 3). No LLM involved: candidates are assumed
already filtered (quantity > 0, condition != faulty, any hard requirements)
by the caller — that filtering is the pipeline's job (Phase 3).

Combinatorics are bounded by `top_n` per category (SPEC.md §6: "bound the
combinatorics ... so it runs quickly with ~200 components"). Candidates
are taken in the order given — ranking candidates by relevance before
calling the engine is the caller's responsibility.
"""

from itertools import combinations

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

# Most desktop builds have 1-2 drives; generating every subset size up to
# a motherboard's actual slot count would require knowing the motherboard
# pick before enumerating storage (the opposite of this function's existing
# per-category, independent-then-filter structure). Capped at 2 instead --
# storage_slots_available (rules.py) still rejects any combo that doesn't
# fit the motherboard actually paired with it in a given build.
MAX_STORAGE_DRIVES = 2

# 2-drive combos are only generated from this many of the top storage
# candidates (always <= top_n) -- combination count grows quadratically
# with pool size, and every single-drive option is still offered from the
# full top_n regardless, so this only bounds how many *pairs* get tried,
# not how many drives are considered at all.
MAX_STORAGE_PAIR_CANDIDATES = 3


def evaluate_build(build: Build, *, headless: bool = False) -> dict[str, RuleResult]:
    results = {rule.__name__: rule(build) for rule in ALL_RULES}
    results["display_output_available"] = display_output_available(build, headless=headless)
    return results


def is_build_valid(rule_results: dict[str, RuleResult]) -> bool:
    return all(result.status != "fail" for result in rule_results.values())


def _storage_combos(
    storage_candidates: list[CandidateComponent],
) -> list[tuple[CandidateComponent, ...]]:
    """Every single-drive option from the full candidate list, plus every
    2-drive combination from a smaller sub-pool (MAX_STORAGE_PAIR_CANDIDATES)
    so combo count grows linearly with top_n rather than quadratically
    (order doesn't matter for compatibility purposes, so combinations
    rather than permutations keeps the count down further)."""
    combos: list[tuple[CandidateComponent, ...]] = [(c,) for c in storage_candidates]
    if MAX_STORAGE_DRIVES >= 2:
        pair_pool = storage_candidates[:MAX_STORAGE_PAIR_CANDIDATES]
        combos.extend(combinations(pair_pool, 2))
    return combos


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
    storage_options = _storage_combos(top(Category.STORAGE))

    builds: list[BuildEvaluation] = []
    for cpu in top(Category.CPU):
        cpu_socket = cpu.specs.socket
        for motherboard in top(Category.MOTHERBOARD):
            board = motherboard.specs
            # Cheap early prunes below mirror a handful of rules.py's "fail"
            # conditions exactly, so the combinatorial tree underneath an
            # already-doomed pairing (e.g. mismatched sockets, or RAM that
            # can't physically fit) is never built or rule-evaluated at
            # all. Each one only ever skips a combination the full
            # evaluation would reject anyway -- missing data on either side
            # always falls through to the full (unknown) check instead, so
            # no build the full rules would have accepted is ever skipped
            # here.
            if cpu_socket is not None and board.socket is not None and cpu_socket != board.socket:
                continue
            for case in top(Category.CASE):
                supported_ff = case.specs.supported_form_factors
                if board.form_factor is not None and supported_ff is not None:
                    if board.form_factor not in supported_ff:
                        continue
                for ram in top(Category.RAM):
                    ram_specs = ram.specs
                    if ram_specs.form is not None and ram_specs.form != "DIMM":
                        continue
                    if ram_specs.memory_type is not None:
                        if board.memory_type is not None and ram_specs.memory_type not in board.memory_type:
                            continue
                        cpu_mem = cpu.specs.memory_type
                        if cpu_mem is not None and ram_specs.memory_type not in cpu_mem:
                            continue
                    if ram_specs.modules is not None and board.memory_slots is not None:
                        if ram_specs.modules > board.memory_slots:
                            continue
                    if (
                        ram_specs.capacity_gb_per_module is not None
                        and ram_specs.modules is not None
                        and board.max_memory_gb is not None
                    ):
                        if ram_specs.capacity_gb_per_module * ram_specs.modules > board.max_memory_gb:
                            continue
                    for storage in storage_options:
                        for psu in top(Category.PSU):
                            for cooler in top(Category.COOLER):
                                for gpu in gpu_options:
                                    build = Build(
                                        cpu=cpu,
                                        motherboard=motherboard,
                                        ram=ram,
                                        storage=list(storage),
                                        psu=psu,
                                        case=case,
                                        cooler=cooler,
                                        gpu=gpu,
                                    )
                                    rule_results = evaluate_build(build, headless=headless)
                                    if is_build_valid(rule_results):
                                        builds.append(BuildEvaluation(build=build, rule_results=rule_results))

    return EngineResult(builds=builds, missing=[])
