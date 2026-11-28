"""Export a run's mutants, static findings and ledger to CSV (CG-20).

Reads the artifacts that the pipeline already writes in ``out/<run_id>/``:
``mutants.json``, ``findings.json`` and ``ledger.jsonl``. It writes ``mutants.csv``,
``findings.csv`` and ``ledger.csv`` next to them. ``results.json`` is written by CG-22
and is not touched here.
"""

import csv
import json
from pathlib import Path
from typing import Final

from codeguard.adapters.ledger import LEDGER_FILE_NAME

MUTANTS_JSON: Final = "mutants.json"
FINDINGS_JSON: Final = "findings.json"
MUTANTS_CSV: Final = "mutants.csv"
FINDINGS_CSV: Final = "findings.csv"
LEDGER_CSV: Final = "ledger.csv"

MUTANT_COLUMNS: Final = (
    "mutant_id",
    "function",
    "status",
    "exit_code",
    "timed_out",
    "failed",
    "duration_seconds",
)
FINDING_COLUMNS: Final = (
    "rule_id",
    "severity",
    "file_path",
    "line",
    "column",
    "message",
    "recommendation",
    "snippet",
)
LEDGER_COLUMNS: Final = (
    "proposal_id",
    "case_ids",
    "source",
    "target",
    "file_name",
    "status",
    "reason",
    "detail",
    "rule_name",
    "code_sha256",
)


def export_run_csv(run_dir: Path) -> dict[str, Path]:
    """Write the three CSV files for ``run_dir`` and return their paths by name.

    Raises ``ValueError`` naming the first missing input artifact.
    """
    mutants = _read_json_list(run_dir / MUTANTS_JSON)
    findings = _read_json_list(run_dir / FINDINGS_JSON)
    ledger = _read_jsonl(run_dir / LEDGER_FILE_NAME)

    outputs = {
        "mutants": run_dir / MUTANTS_CSV,
        "findings": run_dir / FINDINGS_CSV,
        "ledger": run_dir / LEDGER_CSV,
    }
    _write_csv(outputs["mutants"], MUTANT_COLUMNS, mutants)
    _write_csv(outputs["findings"], FINDING_COLUMNS, findings)
    _write_csv(outputs["ledger"], LEDGER_COLUMNS, [_ledger_row(record) for record in ledger])
    return outputs


def _ledger_row(record: dict[str, object]) -> dict[str, object]:
    row = dict(record)
    case_ids = record.get("case_ids")
    if isinstance(case_ids, list):
        row["case_ids"] = ";".join(str(case) for case in case_ids)
    return row


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell(row.get(column)) for column in columns})


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _read_json_list(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise ValueError(f"artifact not found: {path}; run the pipeline first")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError(f"{path}: expected a JSON list of objects")
    return raw


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise ValueError(f"artifact not found: {path}; run the pipeline first")
    records: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{number}: each ledger line must be a JSON object")
        records.append(record)
    return records
