"""Immutable domain models and invariants for CodeGuard AI."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar


def _empty_object_mapping() -> Mapping[str, object]:
    """Return an empty read-only mapping for object values."""
    return MappingProxyType({})


def _empty_float_mapping() -> Mapping[str, float]:
    """Return an empty read-only mapping for float durations."""
    return MappingProxyType({})


def _freeze_mapping[V](mapping: Mapping[str, V]) -> Mapping[str, V]:
    """Return a defensive read-only proxy over a string-keyed mapping."""
    return MappingProxyType(dict(mapping))


def _require_non_empty(value: str, field_name: str) -> None:
    """Validate that a string field contains non-whitespace characters."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_non_negative(value: int | float, field_name: str) -> None:
    """Validate that a numeric field is greater than or equal to zero."""
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_percentage(value: float, field_name: str) -> None:
    """Validate that a percentage field falls within [0.0, 100.0]."""
    if not 0.0 <= value <= 100.0:
        raise ValueError(f"{field_name} must be between 0.0 and 100.0")


class CaseKind(StrEnum):
    """Classification of a contract test case."""

    NORMAL = "normal"
    BOUNDARY = "boundary"
    INVALID = "invalid"


class ProposalSourceKind(StrEnum):
    """Origin of a generated test proposal."""

    TEMPLATE = "template"
    GROQ = "groq"
    DEFECTIVE_SEED = "defective_seed"


class RejectionReason(StrEnum):
    """Canonical rejection reasons emitted by the validation chain."""

    SYNTAX_ERROR = "SYNTAX_ERROR"
    IMPORT_ERROR = "IMPORT_ERROR"
    TARGET_NOT_CALLED = "TARGET_NOT_CALLED"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    NO_ASSERTION = "NO_ASSERTION"
    TAUTOLOGICAL_ASSERTION = "TAUTOLOGICAL_ASSERTION"
    COLLECTION_ERROR = "COLLECTION_ERROR"
    WRONG_EXPECTATION = "WRONG_EXPECTATION"
    GENERATION_ERROR = "GENERATION_ERROR"


class MutantStatus(StrEnum):
    """Classification outcome for an evaluated mutant."""

    KILLED = "KILLED"
    SURVIVED = "SURVIVED"
    EQUIVALENT = "EQUIVALENT"
    INVALID = "INVALID"


class Severity(StrEnum):
    """Severity level of a static analysis finding."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ContractCase:
    """Single input/oracle test case defined in a function contract."""

    case_id: str
    kind: CaseKind
    description: str
    inputs: Mapping[str, object] = field(default_factory=_empty_object_mapping)
    expected: object = None
    expected_exception: str | None = None
    rel_tol: float | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.case_id, "case_id")
        if self.expected_exception is not None:
            _require_non_empty(self.expected_exception, "expected_exception")
        if self.rel_tol is not None:
            _require_non_negative(self.rel_tol, "rel_tol")
        object.__setattr__(self, "inputs", _freeze_mapping(self.inputs))

    @property
    def expects_exception(self) -> bool:
        """Return True when this case expects an exception instead of a value."""
        return self.expected_exception is not None


@dataclass(frozen=True)
class FunctionContract:
    """Contract specification and oracle cases for one reference function."""

    module: str
    name: str
    signature: str
    docstring: str
    cases: tuple[ContractCase, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.module, "module")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.signature, "signature")
        seen_ids: set[str] = set()
        for case in self.cases:
            if case.case_id in seen_ids:
                raise ValueError(f"duplicate case_id in FunctionContract: {case.case_id}")
            seen_ids.add(case.case_id)

    @property
    def qualified_name(self) -> str:
        """Return ``module.name`` for the target function."""
        return f"{self.module}.{self.name}"


@dataclass(frozen=True)
class TestProposal:
    """Generated pytest candidate prior to or after validation."""

    __test__: ClassVar[bool] = False

    proposal_id: str
    target_module: str
    target_function: str
    source: ProposalSourceKind
    code: str
    case_ids: tuple[str, ...] = ()
    file_name: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.proposal_id, "proposal_id")
        _require_non_empty(self.target_module, "target_module")
        _require_non_empty(self.target_function, "target_function")

    @property
    def target_qualified_name(self) -> str:
        """Return ``target_module.target_function``."""
        return f"{self.target_module}.{self.target_function}"


@dataclass(frozen=True)
class ValidationVerdict:
    """Result of evaluating a single TestProposal through the filter chain."""

    proposal_id: str
    valid: bool
    reason: RejectionReason | None = None
    detail: str = ""
    rule_name: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.proposal_id, "proposal_id")
        if self.valid and self.reason is not None:
            raise ValueError("valid verdict must not include a rejection reason")
        if not self.valid and self.reason is None:
            raise ValueError("rejected verdict must include a rejection reason")


@dataclass(frozen=True)
class Mutant:
    """Controlled source code mutation specification from the catalog."""

    mutant_id: str
    module: str
    function: str
    family: str
    description: str
    original: str
    replacement: str
    witness_input: str = ""
    expected_original: str = ""
    expected_mutated: str = ""
    equivalent: bool = False
    equivalence_rationale: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.mutant_id, "mutant_id")
        _require_non_empty(self.module, "module")
        _require_non_empty(self.function, "function")
        _require_non_empty(self.family, "family")
        _require_non_empty(self.original, "original")
        _require_non_empty(self.replacement, "replacement")
        if self.original == self.replacement:
            raise ValueError("replacement must differ from original")
        if self.equivalent:
            _require_non_empty(self.equivalence_rationale, "equivalence_rationale")


@dataclass(frozen=True)
class MutantResult:
    """Evaluation outcome after running the green test suite against a mutant."""

    mutant_id: str
    status: MutantStatus
    killed_by: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    detail: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.mutant_id, "mutant_id")
        _require_non_negative(self.duration_seconds, "duration_seconds")
        if self.status is MutantStatus.KILLED and not self.killed_by:
            raise ValueError("KILLED mutant result must list at least one killing test")
        if self.status is not MutantStatus.KILLED and self.killed_by:
            raise ValueError("non-KILLED mutant result must not list killing tests")


@dataclass(frozen=True)
class Finding:
    """Static security analysis alert emitted by a registered rule."""

    rule_id: str
    file_path: str
    line: int
    column: int = 0
    snippet: str = ""
    message: str = ""
    recommendation: str = ""
    severity: Severity = Severity.HIGH

    def __post_init__(self) -> None:
        _require_non_empty(self.rule_id, "rule_id")
        _require_non_empty(self.file_path, "file_path")
        if self.line < 1:
            raise ValueError("line must be >= 1")
        _require_non_negative(self.column, "column")


def _validate_run_counts(metrics: "RunMetrics") -> None:
    """Validate that all integer counts in RunMetrics are non-negative."""
    count_fields = (
        ("proposals_total", metrics.proposals_total),
        ("proposals_valid", metrics.proposals_valid),
        ("proposals_rejected", metrics.proposals_rejected),
        ("tests_passed", metrics.tests_passed),
        ("tests_failed", metrics.tests_failed),
        ("tests_errors", metrics.tests_errors),
        ("mutants_total", metrics.mutants_total),
        ("mutants_killed", metrics.mutants_killed),
        ("mutants_survived", metrics.mutants_survived),
        ("mutants_equivalent", metrics.mutants_equivalent),
        ("mutants_invalid", metrics.mutants_invalid),
        ("static_findings", metrics.static_findings),
    )
    for field_name, value in count_fields:
        _require_non_negative(value, field_name)


def _validate_run_totals(metrics: "RunMetrics") -> None:
    """Validate that proposal and mutant subtotals match their respective totals."""
    if metrics.proposals_valid + metrics.proposals_rejected != metrics.proposals_total:
        raise ValueError("proposals_valid + proposals_rejected must equal proposals_total")
    mutant_sum = (
        metrics.mutants_killed
        + metrics.mutants_survived
        + metrics.mutants_equivalent
        + metrics.mutants_invalid
    )
    if mutant_sum != metrics.mutants_total:
        raise ValueError("sum of mutant statuses must equal mutants_total")


def _validate_phase_durations(durations: Mapping[str, float]) -> Mapping[str, float]:
    """Validate non-negative phase durations and return a read-only proxy."""
    for phase, seconds in durations.items():
        _require_non_empty(phase, "phase name")
        _require_non_negative(seconds, f"phase_durations_seconds[{phase}]")
    return _freeze_mapping(durations)


@dataclass(frozen=True)
class RunMetrics:
    """Aggregated quality, coverage, mutation, and timing metrics for a run."""

    proposals_total: int
    proposals_valid: int
    proposals_rejected: int
    tests_passed: int
    tests_failed: int
    tests_errors: int
    line_coverage_pct: float
    branch_coverage_pct: float
    mutants_total: int
    mutants_killed: int
    mutants_survived: int
    mutants_equivalent: int
    mutants_invalid: int
    static_findings: int = 0
    phase_durations_seconds: Mapping[str, float] = field(default_factory=_empty_float_mapping)

    def __post_init__(self) -> None:
        _validate_run_counts(self)
        _validate_run_totals(self)
        _require_percentage(self.line_coverage_pct, "line_coverage_pct")
        _require_percentage(self.branch_coverage_pct, "branch_coverage_pct")
        frozen_durations = _validate_phase_durations(self.phase_durations_seconds)
        object.__setattr__(self, "phase_durations_seconds", frozen_durations)

    @property
    def validity_rate_pct(self) -> float:
        """Percentage of proposed tests accepted by the validation filter."""
        if self.proposals_total == 0:
            return 0.0
        return (self.proposals_valid / self.proposals_total) * 100.0

    @property
    def mutants_valid_denominator(self) -> int:
        """Denominator for mutation score excluding equivalent and invalid mutants."""
        return self.mutants_killed + self.mutants_survived

    @property
    def mutation_score_pct(self) -> float:
        """Detected mutants percentage over valid (killed + survived) mutants."""
        denominator = self.mutants_valid_denominator
        if denominator == 0:
            return 0.0
        return (self.mutants_killed / denominator) * 100.0

    @property
    def total_duration_seconds(self) -> float:
        """Sum of recorded durations across all pipeline phases."""
        return sum(self.phase_durations_seconds.values())
