"""Shared dataclasses for the compatibility engine.

Deliberately decoupled from the SQLAlchemy ORM: rules and the engine only
ever see already-filtered candidates (quantity > 0, condition != faulty —
that filtering happens in the pipeline, Phase 3) plus their validated specs,
not the full database row. This keeps compatibility/ independently testable
without a database, as SPEC.md requires.

Simplification: a Build holds exactly one component per category, except
`storage`, which holds 1-2 drives (see engine.py's `MAX_STORAGE_DRIVES`) --
`storage_slots_available` (rules.py) checks the combined count against the
motherboard's M.2/SATA slots, split by interface.
"""

from dataclasses import dataclass
from typing import Literal

from app.schemas.components import ComponentSpecs

RuleStatus = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class CandidateComponent:
    """A single inventory item, reduced to what the compatibility rules need.

    release_year is not used by any compatibility rule (it's not a
    capability, just metadata about the part) -- it rides along so the
    recommend pipeline (Phase 3) can rank/filter by it without a second
    lookup back to the database."""

    id: int
    name: str
    specs: ComponentSpecs
    release_year: int | None = None


@dataclass(frozen=True)
class Build:
    """One candidate machine: a specific component in each slot.

    Every slot but `gpu` is required -- a build without a CPU or a PSU is
    not a build. `storage` is a list because a machine may hold more than
    one drive (engine.MAX_STORAGE_DRIVES), and `gpu` is None for a build
    relying on the CPU's integrated graphics.

    Attributes:
        cpu: The processor.
        motherboard: The board; its socket and memory support constrain most
            of the other slots.
        ram: One memory kit, itself possibly several modules.
        storage: One or more drives.
        psu: The power supply.
        case: The enclosure; its clearances constrain GPU length and cooler
            height.
        cooler: The CPU cooler.
        gpu: A discrete graphics card, or None.
    """

    cpu: CandidateComponent
    motherboard: CandidateComponent
    ram: CandidateComponent
    storage: list[CandidateComponent]
    psu: CandidateComponent
    case: CandidateComponent
    cooler: CandidateComponent
    gpu: CandidateComponent | None = None


@dataclass(frozen=True)
class RuleResult:
    """What one compatibility rule concluded, and why.

    The three-way status is the heart of the design. "unknown" exists
    because a missing specification is genuinely different from an
    incompatibility: the build is still offered, with the gap surfaced as a
    warning, rather than being rejected on data the user never entered.

    Attributes:
        status: "pass", "fail", or "unknown".
        message: Human-readable reason, shown next to the build.
    """

    status: RuleStatus
    message: str


@dataclass(frozen=True)
class BuildEvaluation:
    """A build together with every rule's verdict on it.

    Attributes:
        build: The candidate machine.
        rule_results: Rule name -> result, for all 16 checks.
    """

    build: Build
    rule_results: dict[str, RuleResult]

    @property
    def warnings(self) -> list[str]:
        """Human-readable messages for every rule that could not decide.

        Returns:
            list[str]: One message per rule that returned "unknown", shown to
                the user alongside the build.
        """
        return [result.message for result in self.rule_results.values() if result.status == "unknown"]


@dataclass(frozen=True)
class EngineResult:
    """What the compatibility engine produced from one inventory.

    `builds` and `missing` are alternatives in practice: when a required
    category has no candidates at all, no build can be formed, so the engine
    reports the category by name instead of returning an unexplained empty
    list.

    Attributes:
        builds: Every combination where no rule returned "fail".
        missing: Required categories that had no candidates.
    """

    builds: list[BuildEvaluation]
    missing: list[str]
