"""Compute ``RunMetrics`` and persist ``results.json`` with explicit denominators (CG-22)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codeguard.adapters.execution.junit import parse_junit
from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.domain import RunMetrics
from codeguard.domain.execution import ExecutionOutcome
from codeguard.domain.ledger import LedgerSummary

RESULTS_FILE_NAME = "results.json"
COVERAGE_FILE_NAME = "coverage.json"
_RUN_CONFIG_FILE_NAME = "run_config.json"
_MUTANTS_FILE_NAME = "mutants.json"
_FINDINGS_FILE_NAME = "findings.json"
_JUNIT_FILE_NAME = "junit.xml"


@dataclass(frozen=True)
class MetricsReport:
    """Computed ``RunMetrics`` and path to ``results.json`` for one run."""

    run_id: str
    metrics: RunMetrics
    results_path: Path


class ComputeMetrics:
    """Aggregates run artifacts into immutable ``RunMetrics`` and writes ``results.json``."""

    def execute(self, run_dir: Path) -> MetricsReport:
        """Read available artifacts in ``run_dir``, compute metrics, and write ``results.json``."""
        if not run_dir.is_dir():
            raise ValueError(f"run directory not found: {run_dir}")

        total, valid, rejected, by_source, by_reason = _read_ledger_counts(
            run_dir / LEDGER_FILE_NAME
        )
        passed, failed, errors = _read_junit_counts(run_dir / _JUNIT_FILE_NAME)
        line_pct, branch_pct, cov_available = _read_coverage_metrics(run_dir / COVERAGE_FILE_NAME)
        mut_total, mut_killed, mut_survived, mut_equiv, mut_invalid = _read_mutant_counts(
            run_dir / _MUTANTS_FILE_NAME
        )
        findings_total = _read_findings_count(run_dir / _FINDINGS_FILE_NAME)
        durations = _read_phase_durations(run_dir / _RUN_CONFIG_FILE_NAME)

        metrics = RunMetrics(
            proposals_total=total,
            proposals_valid=valid,
            proposals_rejected=rejected,
            tests_passed=passed,
            tests_failed=failed,
            tests_errors=errors,
            line_coverage_pct=line_pct,
            branch_coverage_pct=branch_pct,
            mutants_total=mut_total,
            mutants_killed=mut_killed,
            mutants_survived=mut_survived,
            mutants_equivalent=mut_equiv,
            mutants_invalid=mut_invalid,
            static_findings=findings_total,
            phase_durations_seconds=durations,
        )
        payload = _build_results_payload(run_dir.name, metrics, by_source, by_reason, cov_available)
        results_path = run_dir / RESULTS_FILE_NAME
        _write_json(results_path, payload)
        return MetricsReport(run_id=run_dir.name, metrics=metrics, results_path=results_path)


def _read_ledger_counts(
    path: Path,
) -> tuple[int, int, int, dict[str, int], dict[str, int]]:
    if not path.is_file():
        return 0, 0, 0, {}, {}
    summary = LedgerSummary.from_entries(JsonlLedger().read(path))
    return (
        summary.total,
        summary.valid,
        summary.rejected,
        dict(summary.by_source),
        dict(summary.by_reason),
    )


def _read_junit_counts(path: Path) -> tuple[int, int, int]:
    if not path.is_file():
        return 0, 0, 0
    tests = parse_junit(path)
    passed = sum(1 for item in tests if item.outcome is ExecutionOutcome.PASSED)
    failed = sum(1 for item in tests if item.outcome is ExecutionOutcome.FAILED)
    errors = sum(1 for item in tests if item.outcome is ExecutionOutcome.ERROR)
    return passed, failed, errors


def _read_coverage_metrics(path: Path) -> tuple[float, float, bool]:
    if not path.is_file():
        return 0.0, 0.0, False
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return 0.0, 0.0, False
    totals = raw.get("totals")
    if isinstance(totals, dict):
        return _coverage_from_totals(totals), _branch_coverage_from_totals(totals), True
    if "line_coverage_pct" in raw or "branch_coverage_pct" in raw:
        return (
            _clamp_pct(raw.get("line_coverage_pct")),
            _clamp_pct(raw.get("branch_coverage_pct")),
            True,
        )
    return 0.0, 0.0, False


def _coverage_from_totals(totals: Mapping[str, object]) -> float:
    num_statements = _non_negative_float(totals.get("num_statements"))
    covered_lines = _non_negative_float(totals.get("covered_lines"))
    if num_statements > 0:
        return round(min(100.0, (covered_lines / num_statements) * 100.0), 4)
    return _clamp_pct(totals.get("percent_covered"))


def _branch_coverage_from_totals(totals: Mapping[str, object]) -> float:
    num_branches = _non_negative_float(totals.get("num_branches"))
    covered_branches = _non_negative_float(totals.get("covered_branches"))
    if num_branches > 0:
        return round(min(100.0, (covered_branches / num_branches) * 100.0), 4)
    return _clamp_pct(totals.get("branch_coverage_pct"))


def _read_mutant_counts(path: Path) -> tuple[int, int, int, int, int]:
    if not path.is_file():
        return 0, 0, 0, 0, 0
    raw = _read_json(path)
    if not isinstance(raw, list):
        return 0, 0, 0, 0, 0

    killed = survived = equivalent = invalid = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "INVALID")).upper()
        if status == "KILLED":
            killed += 1
        elif status == "SURVIVED":
            survived += 1
        elif status == "EQUIVALENT":
            equivalent += 1
        else:
            invalid += 1
    total = killed + survived + equivalent + invalid
    return total, killed, survived, equivalent, invalid


def _read_findings_count(path: Path) -> int:
    if not path.is_file():
        return 0
    raw = _read_json(path)
    return len(raw) if isinstance(raw, list) else 0


def _read_phase_durations(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return {}
    durations = raw.get("phase_durations_seconds")
    if not isinstance(durations, dict):
        return {}
    result: dict[str, float] = {}
    for phase, value in durations.items():
        if (
            isinstance(phase, str)
            and phase.strip()
            and not isinstance(value, bool)
            and isinstance(value, int | float)
            and value >= 0
        ):
            result[phase] = float(value)
    return result


def _build_results_payload(
    run_id: str,
    metrics: RunMetrics,
    by_source: Mapping[str, int],
    by_reason: Mapping[str, int],
    coverage_available: bool,
) -> dict[str, object]:
    timings: dict[str, float] = {
        phase: round(seconds, 6) for phase, seconds in metrics.phase_durations_seconds.items()
    }
    timings["total"] = round(metrics.total_duration_seconds, 6)
    return {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "validity": {
            "proposals_total": metrics.proposals_total,
            "proposals_valid": metrics.proposals_valid,
            "proposals_rejected": metrics.proposals_rejected,
            "denominator": metrics.proposals_total,
            "includes_defective_seeds": by_source.get("defective_seed", 0) > 0,
            "validity_rate_pct": round(metrics.validity_rate_pct, 2),
            "by_source": dict(by_source),
            "by_reason": dict(by_reason),
        },
        "execution": {
            "tests_passed": metrics.tests_passed,
            "tests_failed": metrics.tests_failed,
            "tests_errors": metrics.tests_errors,
        },
        "coverage": {
            "line_coverage_pct": round(metrics.line_coverage_pct, 2),
            "branch_coverage_pct": round(metrics.branch_coverage_pct, 2),
            "available": coverage_available,
        },
        "mutation": {
            "mutants_total": metrics.mutants_total,
            "mutants_killed": metrics.mutants_killed,
            "mutants_survived": metrics.mutants_survived,
            "mutants_equivalent": metrics.mutants_equivalent,
            "mutants_invalid": metrics.mutants_invalid,
            "valid_denominator": metrics.mutants_valid_denominator,
            "excluded_from_denominator": {
                "equivalent": metrics.mutants_equivalent,
                "invalid": metrics.mutants_invalid,
            },
            "mutation_score_pct": round(metrics.mutation_score_pct, 2),
        },
        "static_analysis": {
            "findings_total": metrics.static_findings,
        },
        "timings_seconds": timings,
    }


def _non_negative_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return 0.0
    return float(value)


def _clamp_pct(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return max(0.0, min(100.0, float(value)))


def _read_json(path: Path) -> object:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
