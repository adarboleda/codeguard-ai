"""Tests for PytestSubprocessRunner (CG-16). Each run starts a real pytest subprocess."""

import hashlib
import shutil
from pathlib import Path

import pytest

from codeguard.adapters.execution import JUNIT_FILE_NAME, PytestSubprocessRunner
from codeguard.domain.execution import ExecutionOutcome

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "reference"

IMPORT = "from sciref.numeric import clamp\n\n\n"
PASSING = IMPORT + "def test_inside() -> None:\n    assert clamp(5, 0, 10) == 5.0\n"
FAILING = IMPORT + "def test_wrong() -> None:\n    assert clamp(-3, 0, 10) == 999.0\n"
ERRORING = "def test_uses_missing_fixture(missing) -> None:\n    assert missing\n"


def _write(directory: Path, name: str, code: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(code, encoding="utf-8")
    return path


def _snapshot(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_green_suite(tmp_path: Path) -> None:
    files = [
        _write(tmp_path / "p", "test_a.py", PASSING),
        _write(tmp_path / "p", "test_b.py", PASSING),
    ]

    result = PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out")

    assert result.is_green
    assert (result.exit_code, result.total, result.passed) == (0, 2, 2)
    assert result.junit_path == (tmp_path / "out" / JUNIT_FILE_NAME).resolve()
    assert result.junit_path.is_file()
    assert result.duration_seconds > 0
    assert [t.node_id for t in result.tests] == [
        "tests/test_a.py::test_inside",
        "tests/test_b.py::test_inside",
    ]


def test_failures_and_errors_are_reported(tmp_path: Path) -> None:
    files = [
        _write(tmp_path / "p", "test_ok.py", PASSING),
        _write(tmp_path / "p", "test_fail.py", FAILING),
        _write(tmp_path / "p", "test_err.py", ERRORING),
    ]

    result = PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out")

    assert not result.is_green
    assert result.exit_code == 1
    assert (result.passed, result.failed, result.errors) == (1, 1, 1)
    failing = {t.file_name: t for t in result.failing_tests}
    assert failing["test_fail.py"].outcome is ExecutionOutcome.FAILED
    assert "999.0" in failing["test_fail.py"].message
    assert failing["test_err.py"].outcome is ExecutionOutcome.ERROR


def test_runs_against_the_given_package_root(tmp_path: Path) -> None:
    """CG-18 passes a mutant copy as package_root: the runner must use it, not reference/."""
    mutant_root = tmp_path / "mutant"
    shutil.copytree(REFERENCE_DIR / "sciref", mutant_root / "sciref")
    _write(mutant_root / "sciref", "numeric.py", "def clamp(x, lo, hi):\n    return 999.0\n")
    _write(mutant_root / "sciref", "__init__.py", "")
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    result = PytestSubprocessRunner().run(files, mutant_root, tmp_path / "out")

    assert result.failed == 1
    assert "999.0" in result.failing_tests[0].message


def test_reference_dir_is_never_written(tmp_path: Path) -> None:
    before = _snapshot(REFERENCE_DIR)
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out")

    assert _snapshot(REFERENCE_DIR) == before


def test_timeout_is_reported_not_counted_as_failure(tmp_path: Path) -> None:
    slow = "import time\n\n\ndef test_slow() -> None:\n    time.sleep(30)\n"
    files = [_write(tmp_path / "p", "test_slow.py", slow)]

    result = PytestSubprocessRunner(timeout_seconds=2).run(files, REFERENCE_DIR, tmp_path / "out")

    assert result.timed_out
    assert result.exit_code is None
    assert result.tests == ()
    assert result.detail == "timeout after 2 s"
    assert not result.is_green


def test_file_without_tests_is_not_green(tmp_path: Path) -> None:
    files = [_write(tmp_path / "p", "test_empty.py", "VALUE = 1\n")]

    result = PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out")

    assert result.exit_code == 5  # pytest: no tests collected
    assert result.total == 0
    assert not result.is_green


def test_stale_junit_report_is_replaced(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _write(out, JUNIT_FILE_NAME, "<stale/>")
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    result = PytestSubprocessRunner().run(files, REFERENCE_DIR, out)

    assert result.passed == 1


def test_outer_pytest_options_do_not_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "--this-option-does-not-exist")
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    assert PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out").is_green


def test_invalid_inputs_are_refused(tmp_path: Path) -> None:
    runner = PytestSubprocessRunner()
    a = _write(tmp_path / "one", "test_same.py", PASSING)
    b = _write(tmp_path / "two", "test_same.py", PASSING)

    with pytest.raises(ValueError, match="no test files"):
        runner.run([], REFERENCE_DIR, tmp_path)
    with pytest.raises(ValueError, match=r"duplicate test file names: test_same.py"):
        runner.run([a, b], REFERENCE_DIR, tmp_path)
    with pytest.raises(ValueError, match="test files not found"):
        runner.run([tmp_path / "test_missing.py"], REFERENCE_DIR, tmp_path)
    with pytest.raises(ValueError, match="package root not found"):
        runner.run([a], tmp_path / "nowhere", tmp_path)
    with pytest.raises(ValueError, match="timeout_seconds"):
        PytestSubprocessRunner(timeout_seconds=0)


def test_coverage_measures_only_the_package_with_branches(tmp_path: Path) -> None:
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]
    out = tmp_path / "out"

    result = PytestSubprocessRunner(coverage_package="sciref").run(files, REFERENCE_DIR, out)

    assert result.coverage is not None
    paths = [module.path for module in result.coverage.modules]
    assert paths == [
        "sciref/__init__.py",
        "sciref/numeric.py",
        "sciref/signals.py",
        "sciref/validation.py",
    ]  # the test files themselves are never measured
    numeric = result.coverage.modules[1]
    assert 0 < numeric.line_pct < 100  # one clamp case covers part of numeric.py
    assert 0 < numeric.branch_pct < 100
    assert numeric.missing_lines
    assert (out / "coverage.json").is_file()
    assert (out / "coverage_html" / "index.html").is_file()


def test_no_coverage_unless_requested(tmp_path: Path) -> None:
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    result = PytestSubprocessRunner().run(files, REFERENCE_DIR, tmp_path / "out")

    assert result.coverage is None
    assert not (tmp_path / "out" / "coverage.json").exists()


def test_stale_coverage_reports_are_removed(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _write(out, "coverage.json", '{"files": {}}')
    _write(out / "coverage_html", "stale.html", "old")
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    result = PytestSubprocessRunner(coverage_package="sciref").run(files, REFERENCE_DIR, out)

    assert result.coverage is not None and result.coverage.modules
    assert not (out / "coverage_html" / "stale.html").exists()


@pytest.mark.parametrize("reserved", ["tests", "pytest.ini", ".coveragerc"])
def test_package_root_cannot_use_workspace_names(tmp_path: Path, reserved: str) -> None:
    root = tmp_path / "root"
    shutil.copytree(REFERENCE_DIR / "sciref", root / "sciref")
    (root / reserved).mkdir() if reserved == "tests" else _write(root, reserved, "")
    files = [_write(tmp_path / "p", "test_ok.py", PASSING)]

    with pytest.raises(ValueError, match=f"must not contain: {reserved}"):
        PytestSubprocessRunner().run(files, root, tmp_path / "out")
