"""``codeguard run``: run the validated suite with coverage of sciref (CG-16 PA 04, CG-17 PA 05)."""

from pathlib import Path
from typing import Annotated

import typer

from codeguard.adapters.config import DEFAULT_CONFIG_FILE, load_settings
from codeguard.adapters.execution import (
    COVERAGE_HTML_DIR_NAME,
    COVERAGE_JSON_FILE_NAME,
    SCIREF_PACKAGE_NAME,
    PytestSubprocessRunner,
)
from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.application.run_suite import ExecutionReport, RunSuite
from codeguard.domain.coverage import CoverageReport, CoverageTargets
from codeguard.domain.errors import CodeGuardError
from codeguard.domain.execution import SuiteResult

_MAX_FAILURES_SHOWN = 10
_MAX_MISSING_CHARS = 40


def run_tests(
    run_id: Annotated[
        str, typer.Option("--run-id", help="Corrida ya generada y validada (out/<run_id>/).")
    ],
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio que contiene el paquete sciref."),
    ] = Path("reference"),
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Directorio raíz de salidas (out/).")
    ] = Path("out"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help=f"Archivo de configuración [default: {DEFAULT_CONFIG_FILE}]"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="Segundos máximos de pytest; sustituye a codeguard.toml."),
    ] = None,
) -> None:
    """Ejecuta las propuestas válidas con cobertura de sciref (junit.xml, coverage.json/html)."""
    try:
        run_dir = _run_dir(out, run_id)
        settings = load_settings(config or DEFAULT_CONFIG_FILE, required=config is not None)
        timeout_seconds = settings.runner.timeout_seconds if timeout is None else timeout
        runner = PytestSubprocessRunner(timeout_seconds, coverage_package=SCIREF_PACKAGE_NAME)
        report = RunSuite(runner, JsonlLedger()).execute(
            ledger_path=run_dir / LEDGER_FILE_NAME,
            proposals_dir=run_dir / "proposals",
            package_root=reference_dir,
            output_dir=run_dir,
        )
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error de ejecución: {error}", err=True)
        raise typer.Exit(code=1) from error
    for line in _summary_lines(report):
        typer.echo(line)
    if report.result.coverage is not None:
        for line in _coverage_lines(report.result.coverage, settings.coverage, run_dir):
            typer.echo(line)
    if not report.result.is_green:
        raise typer.Exit(code=1)


def _run_dir(out: Path, run_id: str) -> Path:
    cleaned = run_id.strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid run_id {run_id!r}: must be a single non-empty directory name")
    return out / cleaned


def _summary_lines(report: ExecutionReport) -> list[str]:
    result = report.result
    if result.timed_out:
        return [f"Ejecución cortada: {result.detail} ({len(report.test_files)} archivos)"]
    lines = [
        f"Ejecución: {result.total} pruebas | {result.passed} aprobadas, {result.failed} "
        f"fallidas, {result.errors} errores, {result.skipped} omitidas | "
        f"{result.duration_seconds:.2f} s | junit: {result.junit_path}"
    ]
    lines.extend(_failure_lines(result))
    if result.total == 0:
        lines.append(f"pytest no ejecutó ninguna prueba (exit {result.exit_code}): {result.detail}")
    return lines


def _failure_lines(result: SuiteResult) -> list[str]:
    failing = result.failing_tests
    lines = [
        f"  ✗ {test.node_id} [{test.outcome.value}] {test.message}".rstrip()
        for test in failing[:_MAX_FAILURES_SHOWN]
    ]
    if len(failing) > _MAX_FAILURES_SHOWN:
        lines.append(f"  ... y {len(failing) - _MAX_FAILURES_SHOWN} más (ver junit.xml)")
    return lines


def _coverage_lines(coverage: CoverageReport, targets: CoverageTargets, run_dir: Path) -> list[str]:
    """Per-module table of line and branch coverage, then the total against the targets."""
    lines = [
        "Cobertura de sciref (solo el paquete bajo estudio):",
        f"  {'módulo':<24}{'líneas':>9}{'ramas':>10}   líneas sin cubrir",
    ]
    for module in coverage.modules:
        row = f"  {module.path:<24}{module.line_pct:>7.1f} %{module.branch_pct:>8.1f} %"
        lines.append(f"{row}   {_line_ranges(module.missing_lines)}".rstrip())
    lines.append(f"  {'TOTAL':<24}{coverage.line_pct:>7.1f} %{coverage.branch_pct:>8.1f} %")
    verdict = "✓ cumplida" if coverage.meets(targets) else "✗ NO cumplida"
    lines.append(
        f"  Meta: ≥ {targets.min_line_pct:g} % líneas y ≥ {targets.min_branch_pct:g} % ramas "
        f"→ {verdict}"
    )
    html_index = run_dir / COVERAGE_HTML_DIR_NAME / "index.html"
    lines.append(f"  Informe: {run_dir / COVERAGE_JSON_FILE_NAME} · {html_index}")
    return lines


def _line_ranges(numbers: tuple[int, ...]) -> str:
    """``(3, 4, 5, 9)`` -> ``"3-5, 9"``, shortened with ``...`` if too long."""
    ranges: list[str] = []
    start = previous = None
    for number in [*numbers, None]:
        if number is not None and previous is not None and number == previous + 1:
            previous = number
            continue
        if start is not None:
            ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = number
    text = ", ".join(ranges)
    return text if len(text) <= _MAX_MISSING_CHARS else f"{text[: _MAX_MISSING_CHARS - 3]}..."
