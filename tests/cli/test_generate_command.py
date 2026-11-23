"""CLI tests for ``codeguard generate`` (CG-07, CG-08)."""

from pathlib import Path

from typer.testing import CliRunner, Result

from codeguard.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"

runner = CliRunner()


def test_cli_generate_writes_templates_and_defective_seeds_by_default(tmp_path: Path) -> None:
    result = runner.invoke(
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
            "pa02-demo",
        ],
    )

    assert result.exit_code == 0, result.output
    proposals_dir = tmp_path / "pa02-demo" / "proposals"
    generated_files = {path.name for path in proposals_dir.glob("test_*.py")}
    assert len(generated_files) == 48
    assert "test_seed_syntax_error.py" in generated_files
    assert "test_seed_tautological.py" in generated_files
    assert "48 archivos" in result.output
    assert "run_id=pa02-demo" in result.output


def test_cli_generate_no_seeds_excludes_defective_seeds(tmp_path: Path) -> None:
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
            "only-templates",
            "--no-seeds",
        ],
    )

    assert result.exit_code == 0, result.output
    proposals_dir = tmp_path / "only-templates" / "proposals"
    assert len(list(proposals_dir.glob("test_*.py"))) == 46
    assert "46 archivos" in result.output


def test_cli_generate_creates_default_run_id_directory(tmp_path: Path) -> None:
    result = runner.invoke(
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
        ],
    )

    assert result.exit_code == 0, result.output
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    assert len(list((run_dirs[0] / "proposals").glob("test_*.py"))) == 48


def test_cli_generate_reports_invalid_specs_seeds_and_run_id(tmp_path: Path) -> None:
    missing_specs = runner.invoke(
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
    assert missing_specs.exit_code == 1
    assert "Error de especificación" in missing_specs.output

    missing_seeds = runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(tmp_path / "missing-seeds.yaml"),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--out",
            str(tmp_path),
            "--run-id",
            "bad-seeds",
        ],
    )
    assert missing_seeds.exit_code == 1
    assert "Error de especificación" in missing_seeds.output

    bad_run_id = runner.invoke(
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
    assert bad_run_id.exit_code == 1
    assert "Error de generación" in bad_run_id.output


def _generate(out: Path, run_id: str, *extra: str) -> Result:
    return runner.invoke(
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
            str(out),
            "--run-id",
            run_id,
            *extra,
        ],
    )


def test_cli_generate_refuses_to_reuse_a_run_id(tmp_path: Path) -> None:
    """Regression: regenerating over a run_id left stale seeds next to the new manifest."""
    first = _generate(tmp_path, "demo")
    second = _generate(tmp_path, "demo", "--no-seeds")

    assert first.exit_code == 0, first.output
    assert second.exit_code == 1
    assert "Error de generación" in second.output
    assert "use a new --run-id" in second.output
    proposals_dir = tmp_path / "demo" / "proposals"
    assert len(list(proposals_dir.glob("test_*.py"))) == 48  # first run left intact
