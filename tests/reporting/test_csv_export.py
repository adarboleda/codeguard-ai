"""Tests for the CSV export of a run (CG-20)."""

import csv
import json
from pathlib import Path

import pytest

from codeguard.adapters.reporting.csv_export import export_run_csv

MUTANT = {
    "mutant_id": "M01",
    "function": "weighted_mean",
    "status": "KILLED",
    "exit_code": 1,
    "timed_out": False,
    "failed": 2,
    "duration_seconds": 0.75,
}
FINDING = {
    "rule_id": "CG002",
    "file_path": "src/app.py",
    "line": 7,
    "column": 4,
    "snippet": 'subprocess.run("ls " + p, shell=True)',
    "message": 'subprocess con shell=True, con coma y "comillas"',
    "recommendation": "Pasar la orden como lista",
    "severity": "HIGH",
}
LEDGER = {
    "proposal_id": "p-001",
    "case_ids": ["clamp_cl_01", "clamp_cl_02"],
    "source": "template",
    "target": "clamp",
    "file_name": "test_clamp_01.py",
    "status": "valid",
    "reason": None,
    "detail": "",
    "rule_name": "",
    "code_sha256": "abc123",
}


def _write_run(run_dir: Path, mutants: list, findings: list, ledger: list) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "mutants.json").write_text(json.dumps(mutants), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
    (run_dir / "ledger.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in ledger),
        encoding="utf-8",
    )


def _rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_writes_three_csv_files_with_headers(tmp_path: Path) -> None:
    _write_run(tmp_path, [MUTANT], [FINDING], [LEDGER])

    outputs = export_run_csv(tmp_path)

    assert outputs["mutants"] == tmp_path / "mutants.csv"
    assert outputs["findings"] == tmp_path / "findings.csv"
    assert outputs["ledger"] == tmp_path / "ledger.csv"
    assert _rows(outputs["mutants"])[0] == [
        "mutant_id",
        "function",
        "status",
        "exit_code",
        "timed_out",
        "failed",
        "duration_seconds",
    ]
    assert _rows(outputs["findings"])[0][:3] == ["rule_id", "severity", "file_path"]
    assert _rows(outputs["ledger"])[0][:2] == ["proposal_id", "case_ids"]


def test_mutant_row_has_one_line_per_mutant(tmp_path: Path) -> None:
    _write_run(tmp_path, [MUTANT, {**MUTANT, "mutant_id": "M02", "status": "SURVIVED"}], [], [])

    rows = _rows(export_run_csv(tmp_path)["mutants"])

    assert len(rows) == 3
    assert rows[1] == ["M01", "weighted_mean", "KILLED", "1", "false", "2", "0.75"]
    assert rows[2][0:3] == ["M02", "weighted_mean", "SURVIVED"]


def test_findings_keep_commas_quotes_and_accents_intact(tmp_path: Path) -> None:
    _write_run(tmp_path, [], [FINDING], [])

    rows = _rows(export_run_csv(tmp_path)["findings"])
    header, data = rows[0], rows[1]
    row = dict(zip(header, data, strict=True))

    assert row["message"] == FINDING["message"]
    assert row["snippet"] == FINDING["snippet"]
    assert row["line"] == "7"


def test_ledger_joins_case_ids_with_semicolon(tmp_path: Path) -> None:
    _write_run(tmp_path, [], [], [LEDGER])

    rows = _rows(export_run_csv(tmp_path)["ledger"])
    row = dict(zip(rows[0], rows[1], strict=True))

    assert row["case_ids"] == "clamp_cl_01;clamp_cl_02"
    assert row["reason"] == ""
    assert row["status"] == "valid"


def test_empty_run_still_writes_headers_only(tmp_path: Path) -> None:
    _write_run(tmp_path, [], [], [])

    outputs = export_run_csv(tmp_path)

    assert len(_rows(outputs["mutants"])) == 1
    assert len(_rows(outputs["findings"])) == 1
    assert len(_rows(outputs["ledger"])) == 1


@pytest.mark.parametrize("missing", ["mutants.json", "findings.json", "ledger.jsonl"])
def test_missing_artifact_is_reported_by_name(tmp_path: Path, missing: str) -> None:
    _write_run(tmp_path, [MUTANT], [FINDING], [LEDGER])
    (tmp_path / missing).unlink()

    with pytest.raises(ValueError, match=missing.replace(".", r"\.")):
        export_run_csv(tmp_path)
