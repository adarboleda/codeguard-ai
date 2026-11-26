"""Comparison of proposal sources over the same functions and mutants (CG-33).

Every figure keeps its denominator explicit, as in the rest of the project: rejected
proposals and defective seeds stay in the validity denominator, and mutation is
``killed / (killed + survived)`` with equivalent and invalid mutants reported apart.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

_FULL = 100.0
_KILLED = "KILLED"
_SURVIVED = "SURVIVED"
_EQUIVALENT = "EQUIVALENT"
_INVALID = "INVALID"


def _pct(part: int, whole: int) -> float | None:
    """``part`` over ``whole`` in percent; ``None`` when there is nothing to divide by."""
    return None if whole == 0 else part / whole * _FULL


@dataclass(frozen=True)
class FunctionCounts:
    """Proposals for one function: how many were made and how many were valid."""

    total: int
    valid: int


@dataclass(frozen=True)
class SourceSummary:
    """Everything one run (one proposal source) contributes to the comparison."""

    label: str
    run_id: str
    proposals_total: int
    proposals_valid: int
    seeds_total: int  # defective seeds are part of the denominator (plan, section 8.1)
    seeds_valid: int
    rejected_by_reason: Mapping[str, int]
    per_function: Mapping[str, FunctionCounts]
    tests_passed: int
    tests_failed: int
    tests_errors: int
    line_pct: float | None
    branch_pct: float | None
    mutants: Mapping[str, str]  # mutant id -> status
    mutant_functions: Mapping[str, str]  # mutant id -> function name
    settings: Mapping[str, str]  # model, temperature, tokens... as recorded by the run

    def __post_init__(self) -> None:
        if not self.label.strip() or not self.run_id.strip():
            raise ValueError("label and run_id must not be empty")
        counts = (self.proposals_total, self.proposals_valid, self.seeds_total, self.seeds_valid)
        if min(counts) < 0 or self.proposals_valid > self.proposals_total:
            raise ValueError("proposal counts must be non-negative and valid <= total")
        if self.seeds_valid > self.seeds_total or self.seeds_total > self.proposals_total:
            raise ValueError("seed counts cannot exceed the proposal counts")
        for name in (
            "rejected_by_reason",
            "per_function",
            "mutants",
            "mutant_functions",
            "settings",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def validity_pct(self) -> float | None:
        """Valid over all proposals, defective seeds included."""
        return _pct(self.proposals_valid, self.proposals_total)

    @property
    def validity_without_seeds_pct(self) -> float | None:
        """Valid over the proposals that are not deliberately defective seeds."""
        return _pct(
            self.proposals_valid - self.seeds_valid, self.proposals_total - self.seeds_total
        )

    def mutants_with(self, status: str) -> tuple[str, ...]:
        """Ids of the mutants with the given status, sorted."""
        return tuple(sorted(mid for mid, value in self.mutants.items() if value == status))

    @property
    def killed(self) -> int:
        return len(self.mutants_with(_KILLED))

    @property
    def survived(self) -> int:
        return len(self.mutants_with(_SURVIVED))

    @property
    def equivalent(self) -> int:
        return len(self.mutants_with(_EQUIVALENT))

    @property
    def invalid(self) -> int:
        return len(self.mutants_with(_INVALID))

    @property
    def mutation_denominator(self) -> int:
        """Valid mutants: killed + survived (equivalent and invalid are left out)."""
        return self.killed + self.survived

    @property
    def mutation_score_pct(self) -> float | None:
        return _pct(self.killed, self.mutation_denominator)

    def mutation_for_function(self, function: str) -> tuple[int, int]:
        """``(killed, killed + survived)`` for the mutants of one function."""
        ids = [mid for mid, name in self.mutant_functions.items() if name == function]
        killed = sum(1 for mid in ids if self.mutants[mid] == _KILLED)
        survived = sum(1 for mid in ids if self.mutants[mid] == _SURVIVED)
        return killed, killed + survived


@dataclass(frozen=True)
class ComparisonReport:
    """Two or more sources compared over the same functions and the same mutants."""

    sources: tuple[SourceSummary, ...]

    def __post_init__(self) -> None:
        if len(self.sources) < 2:
            raise ValueError("a comparison needs at least two sources")
        labels = [source.label for source in self.sources]
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate source labels: {labels}")
        first = self.sources[0]
        for other in self.sources[1:]:
            _require_same(first, other, "mutants", set(first.mutants), set(other.mutants))
            _require_same(
                first, other, "functions", set(first.per_function), set(other.per_function)
            )

    @property
    def functions(self) -> tuple[str, ...]:
        return tuple(self.sources[0].per_function)

    @property
    def mutant_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.sources[0].mutants))


def _require_same(
    first: SourceSummary, other: SourceSummary, what: str, left: set[str], right: set[str]
) -> None:
    if left != right:
        only_left, only_right = sorted(left - right), sorted(right - left)
        raise ValueError(
            f"sources are not comparable: different {what} "
            f"({first.label} only: {only_left}; {other.label} only: {only_right})"
        )
