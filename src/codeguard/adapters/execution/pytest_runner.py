"""Run pytest in a subprocess, inside a temporary copy, with a timeout (CG-16).

The package under study and the test files are copied into a fresh temporary
directory, so the original ``reference/`` is never written (no ``__pycache__``,
no ``.pytest_cache``). The JUnit XML report is written to ``output_dir/junit.xml``.
With ``coverage_package`` set, line and branch coverage of that package only is
written to ``output_dir`` as ``coverage.json`` and ``coverage_html/`` (CG-17).

Workspace layout: the contents of ``package_root`` (e.g. ``sciref/``) at the top,
plus ``tests/``, ``pytest.ini`` and ``.coveragerc``.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from codeguard.adapters.execution.coverage import (
    COVERAGE_JSON_FILE_NAME,
    COVERAGE_RC,
    COVERAGE_RC_FILE_NAME,
    clear_coverage_outputs,
    coverage_args,
    parse_coverage_json,
)
from codeguard.adapters.execution.integrity import (
    SCIREF_PACKAGE_NAME,
    verify_sciref_integrity,
)
from codeguard.adapters.execution.junit import parse_junit
from codeguard.domain.coverage import CoverageReport
from codeguard.domain.execution import SuiteResult

JUNIT_FILE_NAME = "junit.xml"
DEFAULT_TIMEOUT_SECONDS = 60.0
_MAX_DETAIL_CHARS = 300
# Isolated config: the repo's own pytest settings must not leak into the generated suite.
# xunit1 adds file/line attributes, used to map each result back to its proposal file.
_PYTEST_INI = "[pytest]\njunit_family = xunit1\n"
_IGNORED_COPY = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
_TESTS_DIR = "tests"
_RESERVED_NAMES = frozenset({_TESTS_DIR, "pytest.ini", COVERAGE_RC_FILE_NAME})


class PytestSubprocessRunner:
    """``SuiteRunner`` that executes ``python -m pytest`` in a temporary workspace."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        python_executable: str = sys.executable,
        extra_args: Sequence[str] = (),
        coverage_package: str | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._python = python_executable
        self._extra_args = tuple(extra_args)
        self._coverage_package = coverage_package  # None: do not measure (e.g. mutants)

    def run(self, test_files: Sequence[Path], package_root: Path, output_dir: Path) -> SuiteResult:
        """Copy, run and parse; a timeout returns a result with ``timed_out=True``."""
        _check_inputs(test_files, package_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dir = output_dir.resolve()
        junit_path = output_dir / JUNIT_FILE_NAME
        junit_path.unlink(missing_ok=True)
        if self._coverage_package:
            clear_coverage_outputs(output_dir)
        guard = (
            verify_sciref_integrity(package_root)
            if (package_root / SCIREF_PACKAGE_NAME).is_dir()
            else contextlib.nullcontext()
        )
        with guard:
            start = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix="codeguard-run-") as tmp:
                workspace = _prepare_workspace(Path(tmp), test_files, package_root)
                try:
                    completed = subprocess.run(
                        self._command(junit_path, output_dir),
                        cwd=workspace,
                        env=_child_env(workspace),
                        capture_output=True,
                        text=True,
                        timeout=self._timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    return SuiteResult(
                        tests=(),
                        exit_code=None,
                        duration_seconds=time.perf_counter() - start,
                        timed_out=True,
                        detail=f"timeout after {self._timeout_seconds:g} s",
                    )
            elapsed = time.perf_counter() - start
            tests = parse_junit(junit_path) if junit_path.is_file() else ()
            return SuiteResult(
                tests=tests,
                exit_code=completed.returncode,
                duration_seconds=elapsed,
                junit_path=junit_path if junit_path.is_file() else None,
                detail="" if tests else _last_line(completed.stdout + completed.stderr),
                coverage=self._read_coverage(output_dir),
            )

    def _read_coverage(self, output_dir: Path) -> CoverageReport | None:
        report = output_dir / COVERAGE_JSON_FILE_NAME
        if not self._coverage_package or not report.is_file():
            return None
        return parse_coverage_json(report)

    def _command(self, junit_path: Path, output_dir: Path) -> list[str]:
        coverage = (
            coverage_args(self._coverage_package, output_dir) if self._coverage_package else []
        )
        return [
            self._python,
            "-m",
            "pytest",
            "tests",
            "-c",
            "pytest.ini",
            "--rootdir",
            ".",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit_path}",
            *coverage,
            *self._extra_args,
        ]


def _check_inputs(test_files: Sequence[Path], package_root: Path) -> None:
    if not test_files:
        raise ValueError("no test files to run")
    names = [path.name for path in test_files]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        raise ValueError(f"duplicate test file names: {', '.join(duplicated)}")
    missing = [str(path) for path in test_files if not path.is_file()]
    if missing:
        raise ValueError(f"test files not found: {', '.join(missing)}")
    if not package_root.is_dir():
        raise ValueError(f"package root not found: {package_root}")
    clashes = sorted(_RESERVED_NAMES & {child.name for child in package_root.iterdir()})
    if clashes:
        raise ValueError(f"package root {package_root} must not contain: {', '.join(clashes)}")


def _prepare_workspace(workspace: Path, test_files: Sequence[Path], package_root: Path) -> Path:
    """Copy package_root's contents to the top, then add ``tests/`` and the configs."""
    shutil.copytree(package_root, workspace, ignore=_IGNORED_COPY, dirs_exist_ok=True)
    tests_dir = workspace / _TESTS_DIR
    tests_dir.mkdir()
    for path in test_files:
        shutil.copy2(path, tests_dir / path.name)
    (workspace / "pytest.ini").write_text(_PYTEST_INI, encoding="utf-8")
    (workspace / COVERAGE_RC_FILE_NAME).write_text(COVERAGE_RC, encoding="utf-8")
    return workspace


def _child_env(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workspace)  # only the copy: never the original reference/
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_ADDOPTS", None)  # options of an outer pytest must not leak in
    return env


def _last_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:_MAX_DETAIL_CHARS] if lines else ""
