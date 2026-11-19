"""Unit tests for immutable domain models and invariants (CG-03)."""

import ast
import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

import codeguard.domain.models as domain_models_module
from codeguard.domain import (
    CaseKind,
    ContractCase,
    Finding,
    FunctionContract,
    Mutant,
    MutantResult,
    MutantStatus,
    ProposalSourceKind,
    RejectionReason,
    RunMetrics,
    Severity,
    TestProposal,
    ValidationVerdict,
)


def _sample_case(case_id: str = "WM-01") -> ContractCase:
    return ContractCase(
        case_id=case_id,
        kind=CaseKind.NORMAL,
        description="Basic weighted mean",
        inputs={"values": [1.0, 3.0], "weights": [1.0, 3.0]},
        expected=2.5,
        rel_tol=1e-9,
    )


def _sample_contract() -> FunctionContract:
    return FunctionContract(
        module="sciref.numeric",
        name="weighted_mean",
        signature="weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float",
        docstring="Compute weighted mean.",
        cases=(_sample_case(),),
    )


def _sample_proposal() -> TestProposal:
    return TestProposal(
        proposal_id="P-01",
        target_module="sciref.numeric",
        target_function="weighted_mean",
        source=ProposalSourceKind.TEMPLATE,
        code="def test_wm() -> None:\n    assert True\n",
        case_ids=("WM-01",),
        file_name="test_weighted_mean.py",
    )


def _sample_verdict() -> ValidationVerdict:
    return ValidationVerdict(proposal_id="P-01", valid=True)


def _sample_mutant() -> Mutant:
    return Mutant(
        mutant_id="M01",
        module="sciref.numeric",
        function="weighted_mean",
        family="numeric",
        description="Divide by len(values) instead of sum(weights)",
        original="sum(weights)",
        replacement="len(values)",
        witness_input="([1, 3], [1, 3])",
        expected_original="2.5",
        expected_mutated="5.0",
    )


def _sample_mutant_result() -> MutantResult:
    return MutantResult(
        mutant_id="M01",
        status=MutantStatus.KILLED,
        killed_by=("test_weighted_mean_normal",),
        duration_seconds=0.12,
    )


def _sample_finding() -> Finding:
    return Finding(
        rule_id="CG001",
        file_path="samples/security/insecure_eval.py",
        line=12,
        column=4,
        snippet="eval(user_expr)",
        message="Non-literal eval call",
        recommendation="Avoid eval on untrusted input",
        severity=Severity.HIGH,
    )


def _sample_metrics() -> RunMetrics:
    return RunMetrics(
        proposals_total=10,
        proposals_valid=8,
        proposals_rejected=2,
        tests_passed=8,
        tests_failed=0,
        tests_errors=0,
        line_coverage_pct=92.5,
        branch_coverage_pct=87.0,
        mutants_total=13,
        mutants_killed=10,
        mutants_survived=2,
        mutants_equivalent=1,
        mutants_invalid=0,
        static_findings=4,
        phase_durations_seconds={"generate": 0.2, "validate": 0.3, "run": 1.5},
    )


@pytest.mark.parametrize(
    ("instance", "field_name", "new_value"),
    [
        (_sample_case(), "expected", 99.0),
        (_sample_contract(), "name", "other"),
        (_sample_proposal(), "code", "pass"),
        (_sample_verdict(), "valid", False),
        (_sample_mutant(), "replacement", "1"),
        (_sample_mutant_result(), "duration_seconds", 9.9),
        (_sample_finding(), "line", 99),
        (_sample_metrics(), "proposals_total", 99),
    ],
)
def test_all_domain_models_are_frozen_dataclasses(
    instance: object,
    field_name: str,
    new_value: object,
) -> None:
    assert is_dataclass(instance)
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, new_value)


def test_contract_case_inputs_is_defensive_read_only_proxy_and_expected_preserves_list() -> None:
    raw_inputs: dict[str, object] = {"values": [2.0, 4.0]}
    expected_list = [0.0, 1.0]
    case = ContractCase(
        case_id="NM-01",
        kind=CaseKind.NORMAL,
        description="Normalize list",
        inputs=raw_inputs,
        expected=expected_list,
    )

    raw_inputs["extra"] = 123
    assert isinstance(case.inputs, MappingProxyType)
    assert "extra" not in case.inputs
    assert isinstance(case.expected, list)
    assert case.expected == [0.0, 1.0]

    with pytest.raises(TypeError):
        cast(dict[str, object], case.inputs)["injected"] = 1


def test_run_metrics_phase_durations_is_defensive_read_only_proxy() -> None:
    raw_durations = {"generate": 0.1}
    metrics = RunMetrics(
        proposals_total=1,
        proposals_valid=1,
        proposals_rejected=0,
        tests_passed=1,
        tests_failed=0,
        tests_errors=0,
        line_coverage_pct=100.0,
        branch_coverage_pct=100.0,
        mutants_total=1,
        mutants_killed=1,
        mutants_survived=0,
        mutants_equivalent=0,
        mutants_invalid=0,
        phase_durations_seconds=raw_durations,
    )

    raw_durations["mutate"] = 5.0
    assert isinstance(metrics.phase_durations_seconds, MappingProxyType)
    assert "mutate" not in metrics.phase_durations_seconds

    with pytest.raises(TypeError):
        cast(dict[str, float], metrics.phase_durations_seconds)["run"] = 2.0


def test_sequence_fields_remain_tuples() -> None:
    contract = _sample_contract()
    proposal = _sample_proposal()
    result = _sample_mutant_result()

    assert isinstance(contract.cases, tuple)
    assert isinstance(proposal.case_ids, tuple)
    assert isinstance(result.killed_by, tuple)


def test_contract_case_and_function_contract_properties_and_validation() -> None:
    exc_case = ContractCase(
        case_id="WM-ERR",
        kind=CaseKind.INVALID,
        description="Empty input raises ValueError",
        inputs={"values": [], "weights": []},
        expected_exception="ValueError",
    )
    assert exc_case.expects_exception is True
    assert _sample_case().expects_exception is False
    assert _sample_contract().qualified_name == "sciref.numeric.weighted_mean"
    assert _sample_proposal().target_qualified_name == "sciref.numeric.weighted_mean"

    with pytest.raises(ValueError, match="case_id"):
        ContractCase(case_id="   ", kind=CaseKind.NORMAL, description="empty id")
    with pytest.raises(ValueError, match="expected_exception"):
        ContractCase(
            case_id="C1",
            kind=CaseKind.INVALID,
            description="blank exc",
            expected_exception="",
        )
    with pytest.raises(ValueError, match="rel_tol"):
        ContractCase(case_id="C1", kind=CaseKind.NORMAL, description="neg tol", rel_tol=-1e-9)
    with pytest.raises(ValueError, match="duplicate case_id"):
        FunctionContract(
            module="sciref.numeric",
            name="clamp",
            signature="clamp(x, lo, hi)",
            docstring="Clamp value.",
            cases=(_sample_case("DUP"), _sample_case("DUP")),
        )


def test_validation_verdict_and_test_proposal_invariants() -> None:
    rejected = ValidationVerdict(
        proposal_id="P-02",
        valid=False,
        reason=RejectionReason.TAUTOLOGICAL_ASSERTION,
        detail="assert True detected",
        rule_name="UsefulAssertionsRule",
    )
    assert rejected.valid is False

    with pytest.raises(ValueError, match="rejection reason"):
        ValidationVerdict(proposal_id="P-01", valid=True, reason=RejectionReason.SYNTAX_ERROR)
    with pytest.raises(ValueError, match="rejection reason"):
        ValidationVerdict(proposal_id="P-01", valid=False, reason=None)
    with pytest.raises(ValueError, match="proposal_id"):
        TestProposal(
            proposal_id="",
            target_module="sciref.numeric",
            target_function="clamp",
            source=ProposalSourceKind.GROQ,
            code="pass",
        )


def test_mutant_and_mutant_result_invariants() -> None:
    eq_mutant = Mutant(
        mutant_id="M03",
        module="sciref.numeric",
        function="clamp",
        family="logic",
        description="x < lo -> x <= lo",
        original="x < lo",
        replacement="x <= lo",
        equivalent=True,
        equivalence_rationale="When x == lo, both branches return lo.",
    )
    assert eq_mutant.equivalent is True

    survived = MutantResult(mutant_id="M04", status=MutantStatus.SURVIVED)
    assert survived.killed_by == ()

    with pytest.raises(ValueError, match="differ"):
        Mutant(
            mutant_id="M99",
            module="sciref.numeric",
            function="clamp",
            family="logic",
            description="noop",
            original="x < lo",
            replacement="x < lo",
        )
    with pytest.raises(ValueError, match="equivalence_rationale"):
        Mutant(
            mutant_id="M03",
            module="sciref.numeric",
            function="clamp",
            family="logic",
            description="missing rationale",
            original="x < lo",
            replacement="x <= lo",
            equivalent=True,
        )
    with pytest.raises(ValueError, match="KILLED"):
        MutantResult(mutant_id="M01", status=MutantStatus.KILLED, killed_by=())
    with pytest.raises(ValueError, match="non-KILLED"):
        MutantResult(
            mutant_id="M03",
            status=MutantStatus.EQUIVALENT,
            killed_by=("test_x",),
        )


def test_finding_invariants() -> None:
    finding = _sample_finding()
    assert finding.severity is Severity.HIGH

    with pytest.raises(ValueError, match="line"):
        Finding(rule_id="CG001", file_path="a.py", line=0)
    with pytest.raises(ValueError, match="column"):
        Finding(rule_id="CG001", file_path="a.py", line=1, column=-1)
    with pytest.raises(ValueError, match="rule_id"):
        Finding(rule_id="", file_path="a.py", line=1)


def test_run_metrics_computed_properties_and_zero_denominators() -> None:
    metrics = _sample_metrics()
    assert metrics.validity_rate_pct == pytest.approx(80.0)
    assert metrics.mutants_valid_denominator == 12
    assert metrics.mutation_score_pct == pytest.approx((10 / 12) * 100.0)
    assert metrics.total_duration_seconds == pytest.approx(2.0)

    empty_metrics = RunMetrics(
        proposals_total=0,
        proposals_valid=0,
        proposals_rejected=0,
        tests_passed=0,
        tests_failed=0,
        tests_errors=0,
        line_coverage_pct=0.0,
        branch_coverage_pct=0.0,
        mutants_total=1,
        mutants_killed=0,
        mutants_survived=0,
        mutants_equivalent=1,
        mutants_invalid=0,
    )
    assert empty_metrics.validity_rate_pct == 0.0
    assert empty_metrics.mutants_valid_denominator == 0
    assert empty_metrics.mutation_score_pct == 0.0
    assert empty_metrics.total_duration_seconds == 0.0


def _build_invalid_metrics(
    *,
    proposals_valid: int = 8,
    mutants_total: int = 13,
    tests_passed: int = 8,
    line_coverage_pct: float = 90.0,
    branch_coverage_pct: float = 85.0,
    phase_durations_seconds: dict[str, float] | None = None,
) -> RunMetrics:
    return RunMetrics(
        proposals_total=10,
        proposals_valid=proposals_valid,
        proposals_rejected=2,
        tests_passed=tests_passed,
        tests_failed=0,
        tests_errors=0,
        line_coverage_pct=line_coverage_pct,
        branch_coverage_pct=branch_coverage_pct,
        mutants_total=mutants_total,
        mutants_killed=10,
        mutants_survived=2,
        mutants_equivalent=1,
        mutants_invalid=0,
        static_findings=0,
        phase_durations_seconds=(
            {"run": 1.0} if phase_durations_seconds is None else phase_durations_seconds
        ),
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _build_invalid_metrics(proposals_valid=7),
        lambda: _build_invalid_metrics(mutants_total=12),
        lambda: _build_invalid_metrics(tests_passed=-1),
        lambda: _build_invalid_metrics(line_coverage_pct=100.1),
        lambda: _build_invalid_metrics(branch_coverage_pct=-0.1),
        lambda: _build_invalid_metrics(phase_durations_seconds={"": 0.1}),
        lambda: _build_invalid_metrics(phase_durations_seconds={"run": -0.5}),
    ],
)
def test_run_metrics_rejects_invalid_values(factory: Callable[[], RunMetrics]) -> None:
    with pytest.raises(ValueError):
        factory()


def test_domain_models_module_has_no_io_or_external_dependencies() -> None:
    source_path = inspect.getsourcefile(domain_models_module)
    assert source_path is not None
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots == {"collections", "dataclasses", "enum", "types", "typing"}
