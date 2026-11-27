"""Tests for ComputeMetrics, RunMetrics denominators, and results.json (CG-22)."""

import json
from pathlib import Path

import pytest

from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.application.compute_metrics import (
    COVERAGE_FILE_NAME,
    RESULTS_FILE_NAME,
    ComputeMetrics,
    _clamp_pct,
    _non_negative_float,
)
from codeguard.domain import ProposalSourceKind, RejectionReason
from codeguard.domain.ledger import LedgerEntry, ProposalStatus


def _ledger_entry(
    proposal_id: str,
    source: ProposalSourceKind,
    status: ProposalStatus,
    reason: RejectionReason | None = None,
) -> LedgerEntry:
    return LedgerEntry(
        proposal_id=proposal_id,
        case_ids=("C-01",),
        source=source,
        target="sciref.numeric.clamp",
        file_name=f"test_{proposal_id}.py",
        status=status,
        reason=reason,
        detail="",
        rule_name="assertions" if reason else "",
        code_sha256="a" * 64,
    )


def _write_synthetic_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        *(
            _ledger_entry(f"tpl-{i}", ProposalSourceKind.TEMPLATE, ProposalStatus.VALID)
            for i in range(46)
        ),
        _ledger_entry(
            "seed-1",
            ProposalSourceKind.DEFECTIVE_SEED,
            ProposalStatus.REJECTED,
            RejectionReason.SYNTAX_ERROR,
        ),
        _ledger_entry(
            "seed-2",
            ProposalSourceKind.DEFECTIVE_SEED,
            ProposalStatus.REJECTED,
            RejectionReason.TAUTOLOGICAL_ASSERTION,
        ),
    ]
    JsonlLedger().write(entries, run_dir)

    testcases = "\n".join(
        f'    <testcase classname="tests.test_x" name="test_{i}" time="0.01"/>' for i in range(46)
    )
    (run_dir / "junit.xml").write_text(
        f'<testsuite tests="46" failures="0" errors="0" skipped="0">\n{testcases}\n</testsuite>\n',
        encoding="utf-8",
    )

    mutants = [
        *({"mutant_id": f"M{i:02d}", "status": "KILLED"} for i in range(1, 11)),
        {"mutant_id": "M11", "status": "SURVIVED"},
        {"mutant_id": "M12", "status": "EQUIVALENT"},
        {"mutant_id": "M13", "status": "INVALID"},
    ]
    (run_dir / "mutants.json").write_text(json.dumps(mutants), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps([{"rule_id": "CG001"}] * 4), encoding="utf-8")
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "phase_durations_seconds": {
                    "generate": 0.1,
                    "validate": 1.2,
                    "run": 0.8,
                    "mutate": 4.5,
                    "scan": 0.02,
                    "report": 0.03,
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / COVERAGE_FILE_NAME).write_text(
        json.dumps(
            {
                "totals": {
                    "num_statements": 100,
                    "covered_lines": 92,
                    "num_branches": 20,
                    "covered_branches": 17,
                }
            }
        ),
        encoding="utf-8",
    )


def test_compute_metrics_computes_denominators_coverage_and_timings(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-metrics"
    _write_synthetic_run(run_dir)

    report = ComputeMetrics().execute(run_dir)

    assert report.results_path == run_dir / RESULTS_FILE_NAME
    assert report.metrics.proposals_total == 48
    assert report.metrics.proposals_valid == 46
    assert report.metrics.proposals_rejected == 2
    assert report.metrics.validity_rate_pct == pytest.approx(46 / 48 * 100.0)
    assert report.metrics.line_coverage_pct == pytest.approx(92.0)
    assert report.metrics.branch_coverage_pct == pytest.approx(85.0)
    assert report.metrics.mutants_total == 13
    assert report.metrics.mutants_valid_denominator == 11
    assert report.metrics.mutation_score_pct == pytest.approx(10 / 11 * 100.0)
    assert report.metrics.static_findings == 4
    assert report.metrics.total_duration_seconds == pytest.approx(6.65)

    data = json.loads(report.results_path.read_text(encoding="utf-8"))
    assert data["validity"]["denominator"] == 48
    assert data["validity"]["includes_defective_seeds"] is True
    assert data["coverage"] == {
        "line_coverage_pct": 92.0,
        "branch_coverage_pct": 85.0,
        "available": True,
    }
    assert data["mutation"]["valid_denominator"] == 11
    assert data["mutation"]["excluded_from_denominator"] == {"equivalent": 1, "invalid": 1}
    assert data["timings_seconds"]["total"] == pytest.approx(6.65)


def test_compute_metrics_supports_direct_coverage_and_absent_coverage(tmp_path: Path) -> None:
    direct_dir = tmp_path / "direct-cov"
    direct_dir.mkdir()
    (direct_dir / LEDGER_FILE_NAME).write_text("", encoding="utf-8")
    (direct_dir / COVERAGE_FILE_NAME).write_text(
        json.dumps({"line_coverage_pct": 88.5, "branch_coverage_pct": 76.0}),
        encoding="utf-8",
    )

    direct_report = ComputeMetrics().execute(direct_dir)
    direct_json = json.loads(direct_report.results_path.read_text(encoding="utf-8"))
    assert direct_json["coverage"] == {
        "line_coverage_pct": 88.5,
        "branch_coverage_pct": 76.0,
        "available": True,
    }

    no_cov_dir = tmp_path / "no-cov"
    no_cov_dir.mkdir()
    no_cov_report = ComputeMetrics().execute(no_cov_dir)
    no_cov_json = json.loads(no_cov_report.results_path.read_text(encoding="utf-8"))
    assert no_cov_json["coverage"] == {
        "line_coverage_pct": 0.0,
        "branch_coverage_pct": 0.0,
        "available": False,
    }


def test_compute_metrics_rejects_missing_run_dir(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"

    with pytest.raises(ValueError, match="run directory not found"):
        ComputeMetrics().execute(missing_dir)


def test_compute_metrics_handles_malformed_artifacts_and_fallback_totals(tmp_path: Path) -> None:
    run_dir = tmp_path / "edge-metrics"
    run_dir.mkdir()
    (run_dir / COVERAGE_FILE_NAME).write_text(
        json.dumps(
            {
                "totals": {
                    "num_statements": 0,
                    "percent_covered": 75.5,
                    "num_branches": 0,
                    "branch_coverage_pct": 50.25,
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "mutants.json").write_text(
        json.dumps(["skip-non-dict", {"mutant_id": "M01", "status": "KILLED"}]),
        encoding="utf-8",
    )
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "phase_durations_seconds": {
                    "generate": 0.4,
                    "bad_bool": True,
                    "bad_neg": -1.0,
                    "": 1.0,
                }
            }
        ),
        encoding="utf-8",
    )

    report = ComputeMetrics().execute(run_dir)
    assert report.metrics.line_coverage_pct == pytest.approx(75.5)
    assert report.metrics.branch_coverage_pct == pytest.approx(50.25)
    assert report.metrics.mutants_total == 1
    assert report.metrics.phase_durations_seconds == {"generate": 0.4}

    bad_dir = tmp_path / "bad-shapes"
    bad_dir.mkdir()
    (bad_dir / COVERAGE_FILE_NAME).write_text("[]", encoding="utf-8")
    (bad_dir / "mutants.json").write_text("{}", encoding="utf-8")
    (bad_dir / "run_config.json").write_text("[]", encoding="utf-8")

    bad_report = ComputeMetrics().execute(bad_dir)
    assert bad_report.metrics.line_coverage_pct == 0.0
    assert bad_report.metrics.mutants_total == 0
    assert bad_report.metrics.phase_durations_seconds == {}

    cfg_bad_durations = tmp_path / "bad-dur"
    cfg_bad_durations.mkdir()
    (cfg_bad_durations / "run_config.json").write_text(
        json.dumps({"phase_durations_seconds": []}),
        encoding="utf-8",
    )
    assert ComputeMetrics().execute(cfg_bad_durations).metrics.phase_durations_seconds == {}

    assert _non_negative_float(True) == 0.0
    assert _non_negative_float(-5) == 0.0
    assert _clamp_pct("bad") == 0.0
    assert _clamp_pct(150.0) == 100.0
