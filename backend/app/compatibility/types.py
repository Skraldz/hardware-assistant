"""Shared dataclasses for the compatibility engine.

Deliberately decoupled from the SQLAlchemy ORM: rules and the engine only
ever see already-filtered candidates (quantity > 0, condition != faulty —
that filtering happens in the pipeline, Phase 3) plus their validated specs,
not the full database row. This keeps compatibility/ independently testable
without a database, as SPEC.md requires.

Simplification: a Build holds exactly one component per category, including
`storage`. SPEC.md's `storage_slots_available` rule is written in terms of
counting multiple drives; Phase 2 treats each build as single-drive and
checks that 1 drive fits the available slots. Multi-drive builds are out of
scope for now (documented in docs/ai-log.md).
"""

from dataclasses import dataclass
from typing import Literal

from app.schemas.components import ComponentSpecs

RuleStatus = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class CandidateComponent:
    """A single inventory item, reduced to what the compatibility rules need."""

    id: int
    name: str
    specs: ComponentSpecs


@dataclass(frozen=True)
class Build:
    cpu: CandidateComponent
    motherboard: CandidateComponent
    ram: CandidateComponent
    storage: CandidateComponent
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
        return [result.message for result in self.rule_results.values() if result.status == "unknown"]


@dataclass(frozen=True)
class EngineResult:
    builds: list[BuildEvaluation]
    missing: list[str]
