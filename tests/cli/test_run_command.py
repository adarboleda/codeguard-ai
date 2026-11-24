"""CLI tests for ``codeguard run`` (CG-16, PA 04): generate -> validate -> run."""

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from codeguard.application.run_suite import ExecutionReport
from codeguard.cli.main import app
from codeguard.cli.run_command import _coverage_lines, _line_ranges, _summary_lines
from codeguard.domain.coverage import CoverageReport, CoverageTargets, ModuleCoverage
from codeguard.domain.execution import SuiteResult

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"
CONFIG_PATH = REPO_ROOT / "codeguard.toml"

runner = CliRunner()


def _invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


def _generate_and_validate(out: Path, run_id: str) -> None:
    common = ["--specs", str(CONTRACTS_PATH), "--reference-dir", str(REFERENCE_DIR)]
    generated = _invoke(
        "generate", *common, "--seeds", str(SEEDS_PATH), "--out", str(out), "--run-id", run_id
    )
    validated = _invoke("validate", *common, "--out", str(out), "--run-id", run_id)
    assert generated.exit_code == 0, generated.output
    assert validated.exit_code == 0, validated.output


def _run(out: Path, run_id: str, *extra: str) -> Result:
    return _invoke(
        "run",
        "--run-id",
        run_id,
        "--reference-dir",
        str(REFERENCE_DIR),
        "--out",
        str(out),
        "--config",
        str(CONFIG_PATH),
        *extra,
    )


@pytest.fixture
def validated_run(tmp_path: Path) -> Path:
    _generate_and_validate(tmp_path, "pa04")
    return tmp_path


def test_run_executes_only_the_valid_proposals(validated_run: Path) -> None:
    result = _run(validated_run, "pa04")

    assert result.exit_code == 0, result.output
    assert (
        "Ejecución: 46 pruebas | 46 aprobadas, 0 fallidas, 0 errores, 0 omitidas" in result.output
    )
    junit = validated_run / "pa04" / "junit.xml"
    assert junit.is_file()
    assert "test_seed_" not in junit.read_text(encoding="utf-8")  # rejected seeds never run


def test_run_reports_coverage_per_module_pa05(validated_run: Path) -> None:
    result = _run(validated_run, "pa04")

    assert result.exit_code == 0, result.output
    for module in ("__init__", "numeric", "signals", "validation"):
        assert f"sciref/{module}.py" in result.output
    assert "TOTAL                     100.0 %   100.0 %" in result.output
    assert "Meta: ≥ 90 % líneas y ≥ 85 % ramas → ✓ cumplida" in result.output
    assert (validated_run / "pa04" / "coverage.json").is_file()
    assert (validated_run / "pa04" / "coverage_html" / "index.html").is_file()


def test_coverage_below_target_is_flagged() -> None:
    coverage = CoverageReport(
        (ModuleCoverage("sciref/numeric.py", 30, 24, 18, 9, (12, 13, 14, 20)),)
    )

    lines = _coverage_lines(coverage, CoverageTargets(90, 85), Path("out/x"))

    assert "  sciref/numeric.py          80.0 %    50.0 %   12-14, 20" in lines
    assert lines[-2] == "  Meta: ≥ 90 % líneas y ≥ 85 % ramas → ✗ NO cumplida"


@pytest.mark.parametrize(
    ("numbers", "text"),
    [
        ((), ""),
        ((7,), "7"),
        ((3, 4, 5, 9, 11, 12), "3-5, 9, 11-12"),
        (tuple(range(1, 100, 2)), "1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21..."),
    ],
)
def test_missing_lines_are_compressed_into_ranges(numbers: tuple[int, ...], text: str) -> None:
    assert _line_ranges(numbers) == text


def test_failing_suite_exits_1_and_lists_failures(validated_run: Path) -> None:
    proposal = validated_run / "pa04" / "proposals" / "test_clamp_cl_01.py"
    code = proposal.read_text(encoding="utf-8")
    proposal.write_text(code.replace("5.0", "6.0"), encoding="utf-8")

    result = _run(validated_run, "pa04")

    assert result.exit_code == 1
    assert "45 aprobadas, 1 fallidas" in result.output
    assert "✗ tests/test_clamp_cl_01.py::test_clamp_cl_01 [failed]" in result.output


def test_many_failures_are_truncated(validated_run: Path) -> None:
    proposals = sorted((validated_run / "pa04" / "proposals").glob("test_[!s]*.py"))[:11]
    for index, proposal in enumerate(proposals):
        proposal.write_text(f"def test_broken_{index}() -> None:\n    assert 1 == 2\n")

    result = _run(validated_run, "pa04")

    assert result.exit_code == 1
    assert "35 aprobadas, 11 fallidas" in result.output
    assert result.output.count("  ✗ tests/") == 10
    assert "... y 1 más (ver junit.xml)" in result.output


def test_timeout_stops_the_run(validated_run: Path) -> None:
    result = _run(validated_run, "pa04", "--timeout", "0.01")

    assert result.exit_code == 1
    assert "Ejecución cortada: timeout after 0.01 s (46 archivos)" in result.output


def test_summary_when_pytest_ran_nothing() -> None:
    report = ExecutionReport(SuiteResult((), 5, 0.2, detail="no tests ran"), (Path("t.py"),))

    lines = _summary_lines(report)

    assert lines[-1] == "pytest no ejecutó ninguna prueba (exit 5): no tests ran"


def test_run_before_validate_is_an_error(tmp_path: Path) -> None:
    result = _run(tmp_path, "never-validated")

    assert result.exit_code == 1
    assert "Error de ejecución: ledger not found" in result.output


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--timeout", "0"), "timeout_seconds must be positive"),
        (("--run-id", "../escape"), "Invalid run_id"),
    ],
)
def test_invalid_options_are_errors(tmp_path: Path, extra: tuple[str, ...], message: str) -> None:
    result = _run(tmp_path, "x", *extra)

    assert result.exit_code == 1
    assert message in result.output


def test_explicit_missing_config_is_an_error(tmp_path: Path) -> None:
    result = _invoke(
        "run", "--run-id", "x", "--out", str(tmp_path), "--config", str(tmp_path / "no.toml")
    )

    assert result.exit_code == 1
    assert "configuration file not found" in result.output
