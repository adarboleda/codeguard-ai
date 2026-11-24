"""pytest-cov options and ``coverage.json`` parsing (CG-17).

Coverage is measured only for the package under study (``--cov=sciref``), with
branches (``--cov-branch``). Outputs in ``output_dir``: ``coverage.json`` (per-module
data, read by the metrics of CG-22) and ``coverage_html/`` (browsable report).
"""

import json
import shutil
from pathlib import Path

from codeguard.domain.coverage import CoverageReport, ModuleCoverage

COVERAGE_JSON_FILE_NAME = "coverage.json"
COVERAGE_HTML_DIR_NAME = "coverage_html"
COVERAGE_RC_FILE_NAME = ".coveragerc"
# relative_files: paths relative to the workspace ("sciref/numeric.py"), not absolute temp
# paths. On Windows coverage.py still writes backslashes; parse_coverage_json normalises them.
COVERAGE_RC = "[run]\nbranch = True\nrelative_files = True\n"


def coverage_args(package: str, output_dir: Path) -> list[str]:
    """pytest options that measure ``package`` and write JSON + HTML to ``output_dir``."""
    return [
        f"--cov={package}",
        "--cov-branch",
        f"--cov-config={COVERAGE_RC_FILE_NAME}",
        f"--cov-report=json:{output_dir / COVERAGE_JSON_FILE_NAME}",
        f"--cov-report=html:{output_dir / COVERAGE_HTML_DIR_NAME}",
    ]


def clear_coverage_outputs(output_dir: Path) -> None:
    """Remove reports of a previous run so stale numbers are never shown."""
    (output_dir / COVERAGE_JSON_FILE_NAME).unlink(missing_ok=True)
    shutil.rmtree(output_dir / COVERAGE_HTML_DIR_NAME, ignore_errors=True)


def parse_coverage_json(path: Path) -> CoverageReport:
    """Read the per-file summaries of a coverage.py JSON report, sorted by path."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        files = raw["files"]
        modules = tuple(sorted((_module(name, data) for name, data in files.items()), key=_by_path))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid coverage JSON {path}: {error}") from error
    return CoverageReport(modules=modules)


def _by_path(module: ModuleCoverage) -> str:
    return module.path


def _module(name: str, data: dict[str, object]) -> ModuleCoverage:
    summary = data["summary"]
    if not isinstance(summary, dict):
        raise TypeError(f"summary of {name} must be an object")
    missing = data.get("missing_lines", [])
    if not isinstance(missing, list):
        raise TypeError(f"missing_lines of {name} must be a list")
    return ModuleCoverage(
        path=name.replace("\\", "/"),
        statements=int(summary["num_statements"]),
        covered_lines=int(summary["covered_lines"]),
        branches=int(summary.get("num_branches", 0)),
        covered_branches=int(summary.get("covered_branches", 0)),
        missing_lines=tuple(int(line) for line in missing),
    )
