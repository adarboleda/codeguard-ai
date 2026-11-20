"""CLI tests for ``codeguard list`` (CG-06)."""

from pathlib import Path

from typer.testing import CliRunner

from codeguard.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"

runner = CliRunner()


def test_cli_list_displays_all_six_functions_and_cases() -> None:
    result = runner.invoke(
        app,
        ["list", "--specs", str(CONTRACTS_PATH), "--reference-dir", str(REFERENCE_DIR)],
    )

    assert result.exit_code == 0, result.output
    assert "6 funciones, 46 casos" in result.output
    for function_name in (
        "weighted_mean",
        "clamp",
        "normalize_minmax",
        "moving_average",
        "threshold_crossings",
        "validate_range",
    ):
        assert function_name in result.output
    for case_id in ("WM-01", "CL-07", "NM-06", "MA-07", "TC-07", "VR-08"):
        assert case_id in result.output


def test_cli_list_reports_missing_specs_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    result = runner.invoke(
        app,
        ["list", "--specs", str(missing), "--reference-dir", str(REFERENCE_DIR)],
    )

    assert result.exit_code == 1
    assert "Error de especificación" in result.output
    assert "not found" in result.output


def test_cli_list_reports_missing_required_field_clearly(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    contract: "Missing signature"
    cases:
      - id: CL-01
        kind: normal
        inputs: {x: 5, lo: 0, hi: 10}
        expected: 5.0
        oracle: "mid"
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["list", "--specs", str(broken), "--reference-dir", str(REFERENCE_DIR)],
    )

    assert result.exit_code == 1
    assert "functions.0.signature" in result.output
