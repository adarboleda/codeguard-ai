"""End-to-end CLI tests integrating ``codeguard generate`` -> ``codeguard validate``."""

from pathlib import Path

from typer.testing import CliRunner

from codeguard.adapters.ledger import JsonlLedger
from codeguard.cli.main import app
from codeguard.domain import RejectionReason
from codeguard.domain.ledger import ProposalStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"

runner = CliRunner()


def test_cli_generate_then_validate_end_to_end_produces_ledger(tmp_path: Path) -> None:
    gen_result = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "s1-e2e",
        ],
    )
    assert gen_result.exit_code == 0, gen_result.output
    assert "48 archivos" in gen_result.output

    val_result = runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "s1-e2e",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )

    assert val_result.exit_code == 0, val_result.output
    assert "46/48 válidas" in val_result.output
    assert "2 rechazadas" in val_result.output
    assert "SYNTAX_ERROR=1" in val_result.output
    assert "TAUTOLOGICAL_ASSERTION=1" in val_result.output

    ledger_path = tmp_path / "s1-e2e" / "ledger.jsonl"
    assert ledger_path.is_file()
    entries = JsonlLedger().read(ledger_path)
    assert len(entries) == 48
    assert sum(1 for entry in entries if entry.status is ProposalStatus.VALID) == 46
    assert sum(1 for entry in entries if entry.status is ProposalStatus.REJECTED) == 2

    by_id = {entry.proposal_id: entry for entry in entries}
    assert by_id["SEED-SYNTAX-01"].status is ProposalStatus.REJECTED
    assert by_id["SEED-SYNTAX-01"].reason is RejectionReason.SYNTAX_ERROR
    assert by_id["SEED-TAUTOLOGY-01"].status is ProposalStatus.REJECTED
    assert by_id["SEED-TAUTOLOGY-01"].reason is RejectionReason.TAUTOLOGICAL_ASSERTION


def test_cli_validate_reports_missing_manifest_invalid_run_id_and_missing_specs(
    tmp_path: Path,
) -> None:
    missing_run = runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "nonexistent",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert missing_run.exit_code == 1
    assert "Error de validación" in missing_run.output
    assert "Proposals manifest not found" in missing_run.output

    bad_run_id = runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "../escape",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert bad_run_id.exit_code == 1
    assert "Error de validación" in bad_run_id.output

    missing_specs = runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "any",
            "--specs",
            str(tmp_path / "missing.yaml"),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert missing_specs.exit_code == 1
    assert "Error de especificación" in missing_specs.output
