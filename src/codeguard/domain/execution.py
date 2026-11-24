"""Results of running a pytest suite: one entry per executed test (CG-16)."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .coverage import CoverageReport


class ExecutionOutcome(StrEnum):
    """Outcome of one executed test, as reported in the JUnit XML."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ExecutedTest:
    """One test reported by pytest, e.g. ``tests/test_clamp_cl_01.py::test_clamp_cl_01``."""

    node_id: str
    file_name: str
    outcome: ExecutionOutcome
    duration_seconds: float
    message: str = ""

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("node_id must not be empty")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")


@dataclass(frozen=True)
class SuiteResult:
    """Outcome of one pytest run over a set of test files."""

    tests: tuple[ExecutedTest, ...]
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False
    junit_path: Path | None = None
    detail: str = ""
    coverage: CoverageReport | None = None  # only when coverage was measured (CG-17)

    def __post_init__(self) -> None:
        if self.timed_out != (self.exit_code is None):
            raise ValueError("exit_code must be None exactly when the run timed out")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")

    def count(self, outcome: ExecutionOutcome) -> int:
        """Number of tests with the given outcome."""
        return sum(1 for test in self.tests if test.outcome is outcome)

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def passed(self) -> int:
        return self.count(ExecutionOutcome.PASSED)

    @property
    def failed(self) -> int:
        return self.count(ExecutionOutcome.FAILED)

    @property
    def errors(self) -> int:
        return self.count(ExecutionOutcome.ERROR)

    @property
    def skipped(self) -> int:
        return self.count(ExecutionOutcome.SKIPPED)

    @property
    def is_green(self) -> bool:
        """True only if pytest finished, ran at least one test, and nothing failed."""
        return (
            not self.timed_out
            and self.exit_code == 0
            and self.total > 0
            and self.failed == 0
            and self.errors == 0
        )

    @property
    def failing_tests(self) -> tuple[ExecutedTest, ...]:
        """Failed or errored tests (for mutants: the tests that killed it)."""
        bad = (ExecutionOutcome.FAILED, ExecutionOutcome.ERROR)
        return tuple(test for test in self.tests if test.outcome in bad)
