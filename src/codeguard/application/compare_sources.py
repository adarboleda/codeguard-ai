"""Build the source comparison from the artifacts of finished runs (CG-33).

Each run must have gone through ``generate``, ``validate``, ``run`` and ``mutate``
(``codeguard all`` does all of them). Nothing is recomputed: every figure is read from the
files the run wrote, so the table can always be traced back to ``out/<run_id>/``.
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from codeguard.adapters.execution import COVERAGE_JSON_FILE_NAME, parse_coverage_json
from codeguard.adapters.execution.junit import parse_junit
from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.adapters.llm import LLM_DIR_NAME
from codeguard.domain import ProposalSourceKind
from codeguard.domain.comparison import ComparisonReport, FunctionCounts, SourceSummary
from codeguard.domain.execution import ExecutionOutcome
from codeguard.domain.ledger import LedgerEntry, LedgerSummary, ProposalStatus

_JUNIT_FILE_NAME = "junit.xml"
_MUTANTS_FILE_NAME = "mutants.json"
_RUN_CONFIG_FILE_NAME = "run_config.json"


def compare_runs(runs: Sequence[tuple[str, Path]]) -> ComparisonReport:
    """Compare ``(label, run_dir)`` pairs; refuses runs with different functions or mutants."""
    return ComparisonReport(tuple(load_source_summary(label, path) for label, path in runs))


def load_source_summary(label: str, run_dir: Path) -> SourceSummary:
    """Read one run's ledger, JUnit, coverage, mutants and recorded settings."""
    if not run_dir.is_dir():
        raise ValueError(f"run directory not found: {run_dir}")
    entries = JsonlLedger().read(run_dir / LEDGER_FILE_NAME)
    summary = LedgerSummary.from_entries(entries)
    seeds = [entry for entry in entries if entry.source is ProposalSourceKind.DEFECTIVE_SEED]
    tests = parse_junit(_require(run_dir, _JUNIT_FILE_NAME, "run"))
    outcomes = Counter(test.outcome for test in tests)
    line_pct, branch_pct = _coverage(run_dir / COVERAGE_JSON_FILE_NAME)
    mutants, functions = _load_mutants(_require(run_dir, _MUTANTS_FILE_NAME, "mutate"))
    return SourceSummary(
        label=label,
        run_id=run_dir.name,
        proposals_total=summary.total,
        proposals_valid=summary.valid,
        seeds_total=len(seeds),
        seeds_valid=sum(1 for entry in seeds if entry.status is ProposalStatus.VALID),
        rejected_by_reason=summary.by_reason,
        per_function=_per_function(entries),
        tests_passed=outcomes[ExecutionOutcome.PASSED],
        tests_failed=outcomes[ExecutionOutcome.FAILED],
        tests_errors=outcomes[ExecutionOutcome.ERROR],
        line_pct=line_pct,
        branch_pct=branch_pct,
        mutants=mutants,
        mutant_functions=functions,
        settings=_settings(run_dir),
    )


def _require(run_dir: Path, file_name: str, command: str) -> Path:
    path = run_dir / file_name
    if not path.is_file():
        raise ValueError(f"{file_name} not found in {run_dir}; run 'codeguard {command}' first")
    return path


def _per_function(entries: Sequence[LedgerEntry]) -> dict[str, FunctionCounts]:
    totals: Counter[str] = Counter()
    valid: Counter[str] = Counter()
    for entry in entries:
        function = entry.target.rsplit(".", 1)[-1]
        totals[function] += 1
        valid[function] += entry.status is ProposalStatus.VALID
    return {function: FunctionCounts(totals[function], valid[function]) for function in totals}


def _coverage(path: Path) -> tuple[float | None, float | None]:
    if not path.is_file():
        return None, None
    report = parse_coverage_json(path)
    return report.line_pct, report.branch_pct


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error


def _load_mutants(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON array of mutant results")
    statuses: dict[str, str] = {}
    functions: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: every mutant result must be a JSON object")
        mutant_id = item.get("mutant_id")
        status = item.get("status")
        function = item.get("function")
        if not (
            isinstance(mutant_id, str) and isinstance(status, str) and isinstance(function, str)
        ):
            raise ValueError(f"{path}: mutant results need string mutant_id, status and function")
        statuses[mutant_id] = status
        functions[mutant_id] = function
    return statuses, functions


def _settings(run_dir: Path) -> dict[str, str]:
    """Model and configuration as recorded by the run itself."""
    llm_dir = run_dir / LLM_DIR_NAME
    records = (
        [_load_json(path) for path in sorted(llm_dir.glob("*.json"))] if llm_dir.is_dir() else []
    )
    dict_records = [record for record in records if isinstance(record, dict)]
    if dict_records:
        return _llm_settings(dict_records)
    settings = {"source": "template"}
    config = run_dir / _RUN_CONFIG_FILE_NAME
    if config.is_file():
        data = _load_json(config)
        if isinstance(data, dict) and data.get("seed") is not None:
            settings["seed"] = str(data["seed"])
    return settings


def _llm_settings(records: Sequence[Mapping[str, object]]) -> dict[str, str]:
    def distinct(key: str) -> str:
        return ", ".join(sorted({str(r[key]) for r in records if r.get(key) is not None}))

    settings = {
        "source": "groq",
        "model": distinct("model"),
        "temperature": distinct("temperature"),
        "endpoint": distinct("base_url"),
        "calls": str(len(records)),
        "failed_calls": str(sum(1 for r in records if r.get("status") != "ok")),
        "tokens": str(sum(_total_tokens(r) for r in records)),
        "date_utc": ", ".join(
            sorted({str(r["requested_at_utc"])[:10] for r in records if r.get("requested_at_utc")})
        ),
    }
    replayed = distinct("replayed_from")
    if replayed:
        settings["replayed_from"] = replayed
    return settings


def _total_tokens(record: Mapping[str, object]) -> int:
    usage = record.get("usage")
    total = usage.get("total_tokens") if isinstance(usage, dict) else None
    return total if isinstance(total, int) else 0
