"""Tests for the coverage domain model (CG-17)."""

import pytest

from codeguard.domain.coverage import CoverageReport, CoverageTargets, ModuleCoverage


def _module(path: str, lines: tuple[int, int], branches: tuple[int, int]) -> ModuleCoverage:
    return ModuleCoverage(path, lines[1], lines[0], branches[1], branches[0])


def test_module_percentages() -> None:
    module = _module("sciref/numeric.py", lines=(27, 30), branches=(9, 18))

    assert module.line_pct == pytest.approx(90.0)
    assert module.branch_pct == pytest.approx(50.0)


def test_nothing_to_cover_counts_as_full() -> None:
    module = _module("sciref/__init__.py", lines=(0, 0), branches=(0, 0))

    assert (module.line_pct, module.branch_pct) == (100.0, 100.0)


def test_totals_are_weighted_by_size_not_averaged() -> None:
    report = CoverageReport(
        (
            _module("sciref/a.py", lines=(10, 10), branches=(2, 2)),
            _module("sciref/b.py", lines=(0, 30), branches=(0, 8)),
        )
    )

    assert (report.statements, report.covered_lines) == (40, 10)
    assert (report.branches, report.covered_branches) == (10, 2)
    assert report.line_pct == pytest.approx(25.0)  # not the 50 % mean of 100 % and 0 %
    assert report.branch_pct == pytest.approx(20.0)


@pytest.mark.parametrize(
    ("lines", "branches", "meets"),
    [
        ((90, 100), (85, 100), True),  # exactly on target
        ((89, 100), (100, 100), False),
        ((100, 100), (84, 100), False),
    ],
)
def test_meets_targets(lines: tuple[int, int], branches: tuple[int, int], meets: bool) -> None:
    report = CoverageReport((_module("sciref/x.py", lines, branches),))

    assert report.meets(CoverageTargets(min_line_pct=90, min_branch_pct=85)) is meets


def test_empty_report_is_full() -> None:
    assert CoverageReport(()).line_pct == 100.0


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("", 1, 1, 0, 0), "path"),
        (("m.py", -1, 0, 0, 0), "non-negative"),
        (("m.py", 1, 2, 0, 0), "cannot exceed"),
        (("m.py", 1, 1, 1, 2), "cannot exceed"),
    ],
)
def test_module_invariants(args: tuple[str, int, int, int, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ModuleCoverage(*args)


@pytest.mark.parametrize(("line", "branch"), [(-1, 50), (50, 101)])
def test_target_must_be_a_percentage(line: float, branch: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        CoverageTargets(line, branch)
