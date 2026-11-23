"""Run pytest in a subprocess, inside a temporary copy, with a timeout (CG-16).

The package under study and the test files are copied into a fresh temporary
directory, so the original ``reference/`` is never written (no ``__pycache__``,
no ``.pytest_cache``). The JUnit XML report is written to ``output_dir/junit.xml``.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from codeguard.adapters.execution.junit import parse_junit
from codeguard.domain.execution import SuiteResult

JUNIT_FILE_NAME = "junit.xml"
DEFAULT_TIMEOUT_SECONDS = 60.0
_MAX_DETAIL_CHARS = 300
# Isolated config: the repo's own pytest settings must not leak into the generated suite.
# xunit1 adds file/line attributes, used to map each result back to its proposal file.
_PYTEST_INI = "[pytest]\njunit_family = xunit1\n"
_IGNORED_COPY = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


class PytestSubprocessRunner:
    """``SuiteRunner`` that executes ``python -m pytest`` in a temporary workspace."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        python_executable: str = sys.executable,
        extra_args: Sequence[str] = (),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._python = python_executable
        self._extra_args = tuple(extra_args)  # e.g. coverage options (CG-17)

    def run(self, test_files: Sequence[Path], package_root: Path, output_dir: Path) -> SuiteResult:
        """Copy, run and parse; a timeout returns a result with ``timed_out=True``."""
        _check_inputs(test_files, package_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        junit_path = (output_dir / JUNIT_FILE_NAME).resolve()
        junit_path.unlink(missing_ok=True)
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="codeguard-run-") as tmp:
            workspace = _prepare_workspace(Path(tmp), test_files, package_root)
            try:
                completed = subprocess.run(
                    self._command(junit_path),
                    cwd=workspace,
                    env=_child_env(workspace / "package"),
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
        )

    def _command(self, junit_path: Path) -> list[str]:
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


def _prepare_workspace(workspace: Path, test_files: Sequence[Path], package_root: Path) -> Path:
    """Layout: ``package/`` (copy of package_root), ``tests/`` and ``pytest.ini``."""
    shutil.copytree(package_root, workspace / "package", ignore=_IGNORED_COPY)
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    for path in test_files:
        shutil.copy2(path, tests_dir / path.name)
    (workspace / "pytest.ini").write_text(_PYTEST_INI, encoding="utf-8")
    return workspace


def _child_env(package_copy: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(package_copy)  # only the copy: never the original reference/
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_ADDOPTS", None)  # options of an outer pytest must not leak in
    return env


def _last_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:_MAX_DETAIL_CHARS] if lines else ""
