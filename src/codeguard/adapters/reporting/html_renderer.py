"""Jinja2 HTML report renderer for ``codeguard report``."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader, StrictUndefined

from codeguard.adapters.execution.coverage import (
    COVERAGE_HTML_DIR_NAME,
    COVERAGE_JSON_FILE_NAME,
    parse_coverage_json,
)
from codeguard.adapters.execution.junit import parse_junit
from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.domain.execution import ExecutionOutcome
from codeguard.domain.ledger import LedgerSummary

REPORT_HTML_FILE_NAME = "report.html"
_TEMPLATE_NAME = "report.html.j2"


@dataclass(frozen=True)
class HtmlReportResult:
    """Path and metadata of a rendered HTML report."""

    run_id: str
    report_path: Path


class JinjaHtmlReportRenderer:
    """Renders ``report.html`` from run artifacts with functional, mutation, and static sections."""

    def __init__(self, *, templates_dir: Path | None = None) -> None:
        loader = (
            FileSystemLoader(templates_dir)
            if templates_dir is not None
            else PackageLoader("codeguard", "templates")
        )
        # Keep autoescape=True explicitly so .html.j2 templates always escape dynamic text.
        self._env = Environment(
            loader=loader,
            autoescape=True,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )

    def render_run(self, run_dir: Path) -> HtmlReportResult:
        """Read available artifacts in ``run_dir`` and write ``report.html``."""
        if not run_dir.is_dir():
            raise ValueError(f"run directory not found: {run_dir}")

        context: dict[str, object] = {
            "run_id": run_dir.name,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "run_config": _load_run_config(run_dir / "run_config.json"),
            "ledger": _load_ledger_context(run_dir / LEDGER_FILE_NAME),
            "execution": _load_junit_context(run_dir / "junit.xml"),
            "coverage": _load_coverage_context(run_dir),
            "mutation": _load_mutation_context(run_dir / "mutants.json"),
            "static_analysis": _load_static_context(run_dir / "findings.json"),
        }
        rendered = self._env.get_template(_TEMPLATE_NAME).render(**context)
        report_path = run_dir / REPORT_HTML_FILE_NAME
        report_path.write_text(rendered, encoding="utf-8")
        return HtmlReportResult(run_id=run_dir.name, report_path=report_path)


def _load_run_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False}
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return {"available": False}
    sciref = raw.get("sciref_sha256")
    combined = sciref.get("combined") if isinstance(sciref, dict) else None
    durations = _extract_durations(raw.get("phase_durations_seconds"))
    return {
        "available": True,
        "seed": raw.get("seed", "—"),
        "sciref_sha256_combined": str(combined) if isinstance(combined, str) else "",
        "phase_durations": durations,
        "total_duration": sum(durations.values()),
    }


def _extract_durations(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(phase): float(val)
        for phase, val in raw.items()
        if not isinstance(val, bool) and isinstance(val, int | float) and val >= 0
    }


def _load_ledger_context(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False}
    entries = JsonlLedger().read(path)
    summary = LedgerSummary.from_entries(entries)
    return {
        "available": True,
        "total": summary.total,
        "valid": summary.valid,
        "rejected": summary.rejected,
        "validity_pct": summary.validity_pct,
        "by_reason": dict(summary.by_reason),
        "by_source": dict(summary.by_source),
        "entries": [
            {
                "proposal_id": entry.proposal_id,
                "case_ids": entry.case_ids,
                "target": entry.target,
                "source": entry.source.value,
                "status": entry.status.value,
                "reason": entry.reason.value if entry.reason else "",
                "detail": entry.detail,
            }
            for entry in entries
        ],
    }


def _load_junit_context(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False}
    tests = parse_junit(path)
    return {
        "available": True,
        "total": len(tests),
        "passed": sum(1 for t in tests if t.outcome is ExecutionOutcome.PASSED),
        "failed": sum(1 for t in tests if t.outcome is ExecutionOutcome.FAILED),
        "errors": sum(1 for t in tests if t.outcome is ExecutionOutcome.ERROR),
        "skipped": sum(1 for t in tests if t.outcome is ExecutionOutcome.SKIPPED),
        "tests": [
            {
                "node_id": test.node_id,
                "outcome": test.outcome.value,
                "duration_seconds": test.duration_seconds,
                "message": test.message,
            }
            for test in tests
        ],
    }


def _load_coverage_context(run_dir: Path) -> dict[str, object]:
    path = run_dir / COVERAGE_JSON_FILE_NAME
    if not path.is_file():
        return {"available": False}
    html_index_exists = (run_dir / COVERAGE_HTML_DIR_NAME / "index.html").is_file()
    try:
        report = parse_coverage_json(path)
    except ValueError:
        return _simplified_coverage_context(path, html_index_exists)
    return {
        "available": True,
        "line_pct": report.line_pct,
        "branch_pct": report.branch_pct,
        "statements": report.statements,
        "covered_lines": report.covered_lines,
        "branches": report.branches,
        "covered_branches": report.covered_branches,
        "html_index_exists": html_index_exists,
        "modules": [
            {
                "path": mod.path,
                "statements": mod.statements,
                "covered_lines": mod.covered_lines,
                "line_pct": mod.line_pct,
                "branches": mod.branches,
                "covered_branches": mod.covered_branches,
                "branch_pct": mod.branch_pct,
                "missing_lines": mod.missing_lines,
            }
            for mod in report.modules
        ],
    }


def _simplified_coverage_context(path: Path, html_index_exists: bool) -> dict[str, object]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return {"available": False}
    if "line_coverage_pct" not in raw and "branch_coverage_pct" not in raw:
        return {"available": False}
    return {
        "available": True,
        "line_pct": _float_or_zero(raw.get("line_coverage_pct")),
        "branch_pct": _float_or_zero(raw.get("branch_coverage_pct")),
        "statements": 0,
        "covered_lines": 0,
        "branches": 0,
        "covered_branches": 0,
        "html_index_exists": html_index_exists,
        "modules": [],
    }


def _load_mutation_context(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False}
    raw = _read_json(path)
    if not isinstance(raw, list):
        return {"available": False}

    outcomes = [_normalize_mutant(item) for item in raw if isinstance(item, dict)]
    killed = sum(1 for item in outcomes if item["status"] == "KILLED")
    survived = sum(1 for item in outcomes if item["status"] == "SURVIVED")
    equivalent = sum(1 for item in outcomes if item["status"] == "EQUIVALENT")
    invalid = len(outcomes) - killed - survived - equivalent
    valid_denominator = killed + survived
    score = (killed / valid_denominator * 100.0) if valid_denominator > 0 else 0.0
    return {
        "available": True,
        "total": len(outcomes),
        "killed": killed,
        "survived": survived,
        "equivalent": equivalent,
        "invalid": invalid,
        "valid_denominator": valid_denominator,
        "mutation_score_pct": score,
        "outcomes": outcomes,
    }


def _normalize_mutant(item: dict[str, object]) -> dict[str, object]:
    status = str(item.get("status", "INVALID")).upper()
    if status not in {"KILLED", "SURVIVED", "EQUIVALENT"}:
        status = "INVALID"
    exit_code = item.get("exit_code")
    failed = item.get("failed", 0)
    return {
        "mutant_id": str(item.get("mutant_id", "UNKNOWN")),
        "function": str(item.get("function", "—")),
        "status": status,
        "exit_code": exit_code if isinstance(exit_code, int) else None,
        "timed_out": bool(item.get("timed_out", False)),
        "failed": failed if isinstance(failed, int) else 0,
        "duration_seconds": _float_or_zero(item.get("duration_seconds")),
    }


def _load_static_context(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False}
    raw = _read_json(path)
    if not isinstance(raw, list):
        return {"available": False}

    findings = [_normalize_finding(item) for item in raw if isinstance(item, dict)]
    by_rule: dict[str, int] = {}
    for item in findings:
        rule_id = str(item["rule_id"])
        by_rule[rule_id] = by_rule.get(rule_id, 0) + 1
    return {
        "available": True,
        "total": len(findings),
        "by_rule": dict(sorted(by_rule.items())),
        "findings": findings,
    }


def _normalize_finding(item: dict[str, object]) -> dict[str, object]:
    return {
        "rule_id": str(item.get("rule_id", "UNKNOWN")),
        "severity": str(item.get("severity", "INFO")).upper(),
        "file_path": str(item.get("file_path", "")),
        "line": item.get("line", 0),
        "column": item.get("column", 0),
        "snippet": str(item.get("snippet", "")),
        "message": str(item.get("message", "")),
        "recommendation": str(item.get("recommendation", "")),
    }


def _float_or_zero(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _read_json(path: Path) -> object:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data
