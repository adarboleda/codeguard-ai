"""Tests for ``mutate``, ``scan``, ``report``, ``all``, run_config.json, and Makefile (CG-23)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from codeguard.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"
CATALOG_PATH = REPO_ROOT / "mutants" / "catalog.yaml"
SAMPLES_DIR = REPO_ROOT / "samples" / "security"
SCIREF_DIR = REFERENCE_DIR / "sciref"

runner = CliRunner()


def test_cli_help_lists_all_pipeline_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command_name in ("list", "generate", "validate", "run", "mutate", "scan", "report", "all"):
        assert command_name in result.output


def test_cli_scan_and_report_commands(tmp_path: Path) -> None:
    scan_result = runner.invoke(
        app,
        [
            "scan",
            "--run-id",
            "scan-only",
            "--target",
            str(SAMPLES_DIR),
            "--target",
            str(SCIREF_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert scan_result.exit_code == 0, scan_result.output
    findings_path = tmp_path / "scan-only" / "findings.json"
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    assert len(findings) == 4
    assert {item["rule_id"] for item in findings} == {"CG001", "CG002"}

    report_result = runner.invoke(
        app,
        ["report", "--run-id", "scan-only", "--out", str(tmp_path)],
    )
    assert report_result.exit_code == 0, report_result.output
    summary_path = tmp_path / "scan-only" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == "scan-only"
    assert summary["static_scan"]["total"] == 4

    missing_report = runner.invoke(
        app,
        ["report", "--run-id", "does-not-exist", "--out", str(tmp_path)],
    )
    assert missing_report.exit_code == 1
    assert "Error de reporte" in missing_report.output


def test_cli_mutate_reports_missing_ledger_and_catalog(tmp_path: Path) -> None:
    missing_ledger = runner.invoke(
        app,
        [
            "mutate",
            "--run-id",
            "no-ledger",
            "--catalog",
            str(CATALOG_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert missing_ledger.exit_code == 1
    assert "Error de mutación" in missing_ledger.output

    run_dir = tmp_path / "no-catalog"
    run_dir.mkdir()
    (run_dir / "ledger.jsonl").write_text("", encoding="utf-8")
    missing_catalog = runner.invoke(
        app,
        [
            "mutate",
            "--run-id",
            "no-catalog",
            "--catalog",
            str(tmp_path / "missing-catalog.yaml"),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert missing_catalog.exit_code == 1
    assert "Error de mutación" in missing_catalog.output


def test_cli_all_reproduces_full_pipeline_and_writes_run_config(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "all",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--catalog",
            str(CATALOG_PATH),
            "--scan-target",
            str(SAMPLES_DIR),
            "--scan-target",
            str(SCIREF_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "full-repro",
            "--seed",
            "123",
        ],
    )

    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "full-repro"
    for rel in (
        "run_config.json",
        "proposals/manifest.json",
        "ledger.jsonl",
        "junit.xml",
        "mutants.json",
        "findings.json",
        "summary.json",
    ):
        assert (run_dir / rel).is_file(), f"missing artifact {rel}"

    run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["run_id"] == "full-repro"
    assert run_config["seed"] == 123
    assert run_config["timeouts"]["runner_timeout_seconds"] == 60.0
    assert set(run_config["versions"]) >= {
        "codeguard",
        "python",
        "pytest",
        "pydantic",
        "jinja2",
        "typer",
        "pyyaml",
    }
    assert set(run_config["sciref_sha256"]["files"]) == {
        "sciref/__init__.py",
        "sciref/numeric.py",
        "sciref/signals.py",
        "sciref/validation.py",
    }
    assert len(run_config["sciref_sha256"]["combined"]) == 64
    assert set(run_config["phase_durations_seconds"]) == {
        "generate",
        "validate",
        "run",
        "mutate",
        "scan",
        "report",
    }

    mutants = json.loads((run_dir / "mutants.json").read_text(encoding="utf-8"))
    assert len(mutants) == 13
    killed = [item for item in mutants if item["status"] == "KILLED"]
    assert len(killed) >= 10
    m03 = next(item for item in mutants if item["mutant_id"] == "M03")
    assert m03["status"] == "SURVIVED"

    findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    assert len(findings) == 4


def test_makefile_exposes_all_target() -> None:
    makefile = REPO_ROOT / "Makefile"
    assert makefile.is_file()
    content = makefile.read_text(encoding="utf-8")
    assert "all:" in content
    assert "\tuv run codeguard all" in content
