"""Tests for the pytest-cov options and the coverage.json parser (CG-17)."""

import json
from pathlib import Path

import pytest

from codeguard.adapters.execution import COVERAGE_HTML_DIR_NAME, COVERAGE_JSON_FILE_NAME
from codeguard.adapters.execution.coverage import (
    clear_coverage_outputs,
    coverage_args,
    parse_coverage_json,
)

REPORT = {
    "meta": {"version": "7.x", "branch_coverage": True},
    "files": {
        "sciref/signals.py": {
            "summary": {
                "num_statements": 8,
                "covered_lines": 6,
                "num_branches": 2,
                "covered_branches": 1,
            },
            "missing_lines": [19, 20],
        },
        "sciref\\numeric.py": {
            "summary": {
                "num_statements": 30,
                "covered_lines": 30,
                "num_branches": 18,
                "covered_branches": 18,
            },
            "missing_lines": [],
        },
    },
    "totals": {"num_statements": 38, "covered_lines": 36},
}


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / COVERAGE_JSON_FILE_NAME
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_modules_are_parsed_sorted_with_posix_paths(tmp_path: Path) -> None:
    report = parse_coverage_json(_write(tmp_path, REPORT))

    assert [module.path for module in report.modules] == ["sciref/numeric.py", "sciref/signals.py"]
    signals = report.modules[1]
    assert (signals.statements, signals.covered_lines) == (8, 6)
    assert (signals.branches, signals.covered_branches) == (2, 1)
    assert signals.missing_lines == (19, 20)
    assert report.line_pct == pytest.approx(36 / 38 * 100)


def test_report_without_branch_data_counts_no_branches(tmp_path: Path) -> None:
    data = {"files": {"m.py": {"summary": {"num_statements": 4, "covered_lines": 4}}}}

    (module,) = parse_coverage_json(_write(tmp_path, data)).modules

    assert (module.branches, module.branch_pct) == (0, 100.0)


@pytest.mark.parametrize(
    "data",
    [
        {"no_files": {}},
        {"files": {"m.py": {}}},
        {"files": {"m.py": {"summary": {"num_statements": 1, "covered_lines": 2}}}},
        {"files": {"m.py": {"summary": "x"}}},
        {
            "files": {
                "m.py": {"summary": {"num_statements": 1, "covered_lines": 1}, "missing_lines": 3}
            }
        },
    ],
)
def test_malformed_report_raises(tmp_path: Path, data: object) -> None:
    with pytest.raises(ValueError, match="invalid coverage JSON"):
        parse_coverage_json(_write(tmp_path, data))


def test_unreadable_report_raises(tmp_path: Path) -> None:
    path = tmp_path / COVERAGE_JSON_FILE_NAME
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid coverage JSON"):
        parse_coverage_json(path)


def test_coverage_args_measure_only_the_package_with_branches(tmp_path: Path) -> None:
    args = coverage_args("sciref", tmp_path)

    assert args[:2] == ["--cov=sciref", "--cov-branch"]
    assert f"--cov-report=json:{tmp_path / COVERAGE_JSON_FILE_NAME}" in args
    assert f"--cov-report=html:{tmp_path / COVERAGE_HTML_DIR_NAME}" in args


def test_clear_removes_previous_reports(tmp_path: Path) -> None:
    (tmp_path / COVERAGE_JSON_FILE_NAME).write_text("{}", encoding="utf-8")
    (tmp_path / COVERAGE_HTML_DIR_NAME).mkdir()
    (tmp_path / COVERAGE_HTML_DIR_NAME / "index.html").write_text("old", encoding="utf-8")

    clear_coverage_outputs(tmp_path)
    clear_coverage_outputs(tmp_path)  # idempotent

    assert list(tmp_path.iterdir()) == []
