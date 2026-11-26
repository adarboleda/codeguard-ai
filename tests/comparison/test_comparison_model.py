"""Tests for the comparison domain model (CG-33)."""

from typing import Any

import pytest

from codeguard.domain.comparison import ComparisonReport, FunctionCounts, SourceSummary


def _summary(label: str = "A", **overrides: Any) -> SourceSummary:
    values: dict[str, Any] = {
        "label": label,
        "run_id": "run-" + label.lower(),
        "proposals_total": 10,
        "proposals_valid": 8,
        "seeds_total": 2,
        "seeds_valid": 0,
        "rejected_by_reason": {"SYNTAX_ERROR": 1, "NO_ASSERTION": 1},
        "per_function": {"f": FunctionCounts(6, 5), "g": FunctionCounts(4, 3)},
        "tests_passed": 8,
        "tests_failed": 0,
        "tests_errors": 0,
        "line_pct": 98.0,
        "branch_pct": 96.0,
        "mutants": {"M1": "KILLED", "M2": "SURVIVED", "M3": "EQUIVALENT", "M4": "KILLED"},
        "mutant_functions": {"M1": "f", "M2": "f", "M3": "g", "M4": "g"},
        "settings": {"source": "template"},
    }
    values.update(overrides)
    return SourceSummary(**values)


def test_validity_keeps_seeds_in_the_denominator() -> None:
    source = _summary()

    assert source.validity_pct == pytest.approx(80.0)
    assert source.validity_without_seeds_pct == pytest.approx(100.0)  # 8 valid of 8 non-seeds


def test_mutation_score_excludes_equivalent_and_invalid() -> None:
    source = _summary(
        mutants={"M1": "KILLED", "M2": "SURVIVED", "M3": "EQUIVALENT", "M4": "INVALID"},
        mutant_functions={"M1": "f", "M2": "f", "M3": "g", "M4": "g"},
    )

    assert (source.killed, source.survived, source.equivalent, source.invalid) == (1, 1, 1, 1)
    assert source.mutation_denominator == 2
    assert source.mutation_score_pct == pytest.approx(50.0)
    assert source.mutants_with("SURVIVED") == ("M2",)


def test_mutation_for_one_function() -> None:
    source = _summary()

    assert source.mutation_for_function("f") == (1, 2)
    assert source.mutation_for_function("g") == (1, 1)  # M3 is equivalent: not in the count
    assert source.mutation_for_function("unknown") == (0, 0)


def test_empty_denominators_give_none() -> None:
    source = _summary(
        proposals_total=0,
        proposals_valid=0,
        seeds_total=0,
        mutants={"M1": "EQUIVALENT"},
        mutant_functions={"M1": "f"},
    )

    assert source.validity_pct is None
    assert source.validity_without_seeds_pct is None
    assert source.mutation_score_pct is None


def test_summary_is_read_only() -> None:
    source = _summary()

    with pytest.raises(TypeError):
        source.mutants["M9"] = "KILLED"  # type: ignore[index]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"label": " "}, "label and run_id"),
        ({"proposals_valid": 11}, "valid <= total"),
        ({"proposals_total": -1, "proposals_valid": -1}, "non-negative"),
        ({"seeds_valid": 3}, "seed counts"),
        ({"seeds_total": 11}, "seed counts"),
    ],
)
def test_invariants(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _summary(**changes)


def test_report_exposes_shared_functions_and_mutants() -> None:
    report = ComparisonReport((_summary("A"), _summary("B")))

    assert report.functions == ("f", "g")
    assert report.mutant_ids == ("M1", "M2", "M3", "M4")


def test_report_needs_two_distinct_sources() -> None:
    with pytest.raises(ValueError, match="at least two"):
        ComparisonReport((_summary("A"),))
    with pytest.raises(ValueError, match="duplicate source labels"):
        ComparisonReport((_summary("A"), _summary("A")))


def test_report_refuses_different_mutants() -> None:
    other = _summary(
        "B",
        mutants={"M1": "KILLED", "M9": "KILLED"},
        mutant_functions={"M1": "f", "M9": "f"},
    )

    with pytest.raises(ValueError, match=r"different mutants.*A only: \['M2', 'M3', 'M4'\]"):
        ComparisonReport((_summary("A"), other))


def test_report_refuses_different_functions() -> None:
    other = _summary("B", per_function={"f": FunctionCounts(1, 1)})

    with pytest.raises(ValueError, match=r"different functions.*A only: \['g'\]"):
        ComparisonReport((_summary("A"), other))
