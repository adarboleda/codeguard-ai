"""Tests for the execution domain model (CG-16)."""

import pytest

from codeguard.domain.execution import ExecutedTest, ExecutionOutcome, SuiteResult


def _test(outcome: ExecutionOutcome, name: str = "t") -> ExecutedTest:
    return ExecutedTest(f"tests/test_x.py::{name}", "test_x.py", outcome, 0.01)


def test_counts_and_failing_tests() -> None:
    result = SuiteResult(
        tests=(
            _test(ExecutionOutcome.PASSED, "a"),
            _test(ExecutionOutcome.FAILED, "b"),
            _test(ExecutionOutcome.ERROR, "c"),
            _test(ExecutionOutcome.SKIPPED, "d"),
        ),
        exit_code=1,
        duration_seconds=0.5,
    )

    assert (result.total, result.passed, result.failed, result.errors, result.skipped) == (
        4,
        1,
        1,
        1,
        1,
    )
    assert [t.node_id for t in result.failing_tests] == [
        "tests/test_x.py::b",
        "tests/test_x.py::c",
    ]
    assert not result.is_green


@pytest.mark.parametrize(
    ("tests", "exit_code", "green"),
    [
        ((_test(ExecutionOutcome.PASSED),), 0, True),
        ((_test(ExecutionOutcome.PASSED), _test(ExecutionOutcome.SKIPPED)), 0, True),
        ((), 5, False),  # nothing ran
        ((_test(ExecutionOutcome.PASSED),), 2, False),  # pytest interrupted
    ],
)
def test_is_green(tests: tuple[ExecutedTest, ...], exit_code: int, green: bool) -> None:
    assert SuiteResult(tests, exit_code, 0.1).is_green is green


def test_timeout_must_have_no_exit_code() -> None:
    assert not SuiteResult((), None, 2.0, timed_out=True).is_green
    with pytest.raises(ValueError, match="exit_code must be None"):
        SuiteResult((), 0, 2.0, timed_out=True)
    with pytest.raises(ValueError, match="exit_code must be None"):
        SuiteResult((), None, 2.0)


def test_invariants() -> None:
    with pytest.raises(ValueError, match="node_id"):
        ExecutedTest(" ", "test_x.py", ExecutionOutcome.PASSED, 0.0)
    with pytest.raises(ValueError, match="duration_seconds"):
        ExecutedTest("t", "test_x.py", ExecutionOutcome.PASSED, -1.0)
    with pytest.raises(ValueError, match="duration_seconds"):
        SuiteResult((), 0, -0.1)
