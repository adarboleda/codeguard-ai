"""CLI tests for ``codeguard generate`` (CG-07)."""

from pathlib import Path

from typer.testing import CliRunner

from codeguard.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"

runner = CliRunner()


def test_cli_generate_writes_all_proposals_for_explicit_run_id(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "pa02-demo",
        ],
    )

    assert result.exit_code == 0, result.output
    proposals_dir = tmp_path / "pa02-demo" / "proposals"
    generated_files = sorted(proposals_dir.glob("test_*.py"))
    assert len(generated_files) == 46
    assert len(generated_files) >= 26
    assert "46 archivos" in result.output
    assert "run_id=pa02-demo" in result.output


def test_cli_generate_creates_default_run_id_directory(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    assert len(list((run_dirs[0] / "proposals").glob("test_*.py"))) == 46


def test_cli_generate_reports_invalid_specs_and_invalid_run_id(tmp_path: Path) -> None:
    missing_result = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(tmp_path / "missing.yaml"),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "bad-spec",
        ],
    )
    assert missing_result.exit_code == 1
    assert "Error de especificación" in missing_result.output

    bad_run_id_result = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "../escape",
        ],
    )
    assert bad_run_id_result.exit_code == 1
    assert "Error de generación" in bad_run_id_result.output
