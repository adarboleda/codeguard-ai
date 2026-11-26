"""Tests for the mutant classifier (CG-18) with a fake suite runner."""

from collections.abc import Callable
from pathlib import Path

import pytest

from codeguard.adapters.mutation.applier import MutantSpec, load_catalog
from codeguard.adapters.mutation.evaluator import BaselineNotGreenError, evaluate_mutants
from codeguard.domain import MutantStatus
from codeguard.domain.execution import ExecutedTest, ExecutionOutcome, SuiteResult

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "reference"
CATALOG = REPO_ROOT / "mutants" / "catalog.yaml"
TEST_FILES = (Path("out/tests/test_clamp.py"),)

CLAMP_SPEC = MutantSpec(id="X1", function="clamp", original="if x > hi:", mutated="if x >= hi:")


def suite(
    *outcomes: tuple[str, ExecutionOutcome],
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> SuiteResult:
    tests = tuple(
        ExecutedTest(node_id=node, file_name="test_clamp.py", outcome=out, duration_seconds=0.1)
        for node, out in outcomes
    )
    return SuiteResult(
        tests=tests,
        exit_code=None if timed_out else exit_code,
        duration_seconds=0.5,
        timed_out=timed_out,
    )


GREEN = suite(("tests/test_clamp.py::test_a", ExecutionOutcome.PASSED))


class FakeRunner:
    """Answers the baseline (root == REFERENCE) with ``baseline`` and mutants with ``behavior``."""

    def __init__(
        self,
        behavior: Callable[[Path], SuiteResult],
        baseline: SuiteResult = GREEN,
    ) -> None:
        self.behavior = behavior
        self.baseline = baseline
        self.calls: list[Path] = []

    def run(self, test_files: object, package_root: Path, output_dir: Path) -> SuiteResult:
        self.calls.append(package_root)
        if package_root == REFERENCE:
            return self.baseline
        return self.behavior(package_root)


def _always(result: SuiteResult) -> Callable[[Path], SuiteResult]:
    return lambda _root: result


def _evaluate(specs: list[MutantSpec], runner: FakeRunner, out: Path) -> tuple:
    return evaluate_mutants(specs, REFERENCE, TEST_FILES, runner, out)


def test_refuses_to_run_mutants_when_baseline_is_not_green(tmp_path: Path) -> None:
    red = suite(("tests/test_clamp.py::test_a", ExecutionOutcome.FAILED))
    runner = FakeRunner(_always(GREEN), baseline=red)

    with pytest.raises(BaselineNotGreenError):
        _evaluate([CLAMP_SPEC], runner, tmp_path)
    assert runner.calls == [REFERENCE]


def test_failing_test_kills_mutant_and_records_its_node_id(tmp_path: Path) -> None:
    killer = suite(("tests/test_clamp.py::test_a", ExecutionOutcome.FAILED), exit_code=1)
    runner = FakeRunner(_always(killer))

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.KILLED
    assert result.killed_by == ("tests/test_clamp.py::test_a",)


def test_green_suite_leaves_mutant_alive(tmp_path: Path) -> None:
    runner = FakeRunner(_always(GREEN))

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.SURVIVED
    assert result.killed_by == ()


def test_timeout_is_invalid_not_a_detection(tmp_path: Path) -> None:
    runner = FakeRunner(_always(suite(timed_out=True)))

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.INVALID
    assert result.killed_by == ()


def test_import_or_collection_error_is_invalid_not_a_detection(tmp_path: Path) -> None:
    broken = suite(("tests/test_clamp.py::test_a", ExecutionOutcome.ERROR), exit_code=2)
    runner = FakeRunner(_always(broken))

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.INVALID
    assert result.killed_by == ()


def test_run_with_no_tests_executed_is_invalid(tmp_path: Path) -> None:
    runner = FakeRunner(_always(suite(exit_code=5)))

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.INVALID


def test_nonzero_exit_without_failing_tests_is_invalid(tmp_path: Path) -> None:
    runner = FakeRunner(
        _always(suite(("tests/test_clamp.py::test_a", ExecutionOutcome.PASSED), exit_code=3))
    )

    (result,) = _evaluate([CLAMP_SPEC], runner, tmp_path)

    assert result.status is MutantStatus.INVALID


def test_snippet_not_found_is_invalid_and_the_mutant_is_never_run(tmp_path: Path) -> None:
    missing = MutantSpec(id="X2", function="clamp", original="no existe", mutated="x")
    runner = FakeRunner(_always(suite(("t", ExecutionOutcome.FAILED), exit_code=1)))

    (result,) = _evaluate([missing], runner, tmp_path)

    assert result.status is MutantStatus.INVALID
    assert runner.calls == [REFERENCE]


def test_equivalent_mutant_is_reported_without_running_it(tmp_path: Path) -> None:
    equivalent = MutantSpec(
        id="X3", function="clamp", original="if x > hi:", mutated="if x >= hi:", equivalent=True
    )
    runner = FakeRunner(_always(suite(("t", ExecutionOutcome.FAILED), exit_code=1)))

    (result,) = _evaluate([equivalent], runner, tmp_path)

    assert result.status is MutantStatus.EQUIVALENT
    assert runner.calls == [REFERENCE]


def test_real_catalog_gives_twelve_killed_and_one_equivalent(tmp_path: Path) -> None:
    killer = suite(("tests/test_clamp.py::test_a", ExecutionOutcome.FAILED), exit_code=1)
    runner = FakeRunner(_always(killer))

    results = _evaluate(list(load_catalog(CATALOG)), runner, tmp_path)

    statuses = [r.status for r in results]
    assert len(results) == 13
    assert statuses.count(MutantStatus.KILLED) == 12
    assert [r.mutant_id for r in results if r.status is MutantStatus.EQUIVALENT] == ["M03"]


def test_catalog_marks_only_m03_as_equivalent() -> None:
    assert [s.id for s in load_catalog(CATALOG) if s.equivalent] == ["M03"]
