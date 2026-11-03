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
    status: RuleStatus
    message: str


@dataclass(frozen=True)
class BuildEvaluation:
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
    builds: list[BuildEvaluation]
    missing: list[str]
