"""Typer CLI commands for ``mutate``, ``scan``, ``report``, and ``all`` (CG-23)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from codeguard.adapters.config import DEFAULT_CONFIG_FILE, load_settings
from codeguard.application.run_pipeline import (
    DEFAULT_SEED,
    PipelineOptions,
    RunPipeline,
    build_summary_report,
    run_mutation_stage,
    run_scan_stage,
)
from codeguard.domain.errors import CodeGuardError

DEFAULT_CATALOG_PATH = Path("mutants/catalog.yaml")
DEFAULT_SCAN_TARGETS = (Path("samples/security"), Path("reference/sciref"))


def _resolve_run_id(run_id: str | None) -> str:
    if run_id is None:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    cleaned = run_id.strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid run_id {run_id!r}: must be a single non-empty directory name")
    return cleaned


def _resolve_timeouts(config: Path | None, timeout: float | None) -> tuple[float, float]:
    settings = load_settings(config or DEFAULT_CONFIG_FILE, required=config is not None)
    resolved = settings.runner.timeout_seconds if timeout is None else timeout
    if resolved <= 0:
        raise ValueError("timeout must be positive")
    return resolved, settings.runner.import_timeout_seconds


def _resolve_timeout(config: Path | None, timeout: float | None) -> float:
    return _resolve_timeouts(config, timeout)[0]


def mutate_command(
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Corrida ya generada y validada (out/<run_id>/)."),
    ],
    catalog: Annotated[
        Path,
        typer.Option("--catalog", "-c", help="Ruta al catálogo YAML de mutantes."),
    ] = DEFAULT_CATALOG_PATH,
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio raíz del paquete bajo estudio."),
    ] = Path("reference"),
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = Path("out"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help=f"Archivo de configuración [default: {DEFAULT_CONFIG_FILE}]"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="Segundos máximos de pytest por mutante."),
    ] = None,
) -> None:
    """Evalúa los mutantes del catálogo contra las propuestas válidas de out/<run_id>/."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        timeout_seconds = _resolve_timeout(config, timeout)
        report = run_mutation_stage(out / resolved_run_id, catalog, reference_dir, timeout_seconds)
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error de mutación: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Mutantes evaluados: {report.killed}/{report.total} detectados "
        f"({report.survived} sobrevivientes, {report.timed_out_count} timeouts) "
        f"| archivo: {report.output_path}"
    )


def scan_command(
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Identificador de corrida en out/<run_id>/."),
    ],
    target: Annotated[
        list[Path] | None,
        typer.Option("--target", "-t", help="Rutas a escanear (repetible)."),
    ] = None,
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = Path("out"),
) -> None:
    """Ejecuta las reglas estáticas CG001/CG002 y guarda out/<run_id>/findings.json."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        targets = tuple(target) if target else DEFAULT_SCAN_TARGETS
        report = run_scan_stage(out / resolved_run_id, targets)
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error de escaneo: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Escaneo estático: {len(report.findings)} hallazgos | archivo: {report.output_path}"
    )


def report_command(
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Identificador de corrida en out/<run_id>/."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = Path("out"),
) -> None:
    """Consolida los artefactos existentes de out/<run_id>/ en summary, results y report.html."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        summary = build_summary_report(out / resolved_run_id)
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error de reporte: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Resumen generado (run_id={summary.run_id}) en {summary.summary_path}, "
        f"{summary.summary_path.parent / 'results.json'} y "
        f"{summary.summary_path.parent / 'report.html'}"
    )


def all_command(
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Identificador de corrida; por defecto marca temporal UTC."),
    ] = None,
    specs: Annotated[
        Path,
        typer.Option("--specs", "-s", help="Ruta al archivo YAML de contratos."),
    ] = Path("specs/contracts.yaml"),
    seeds: Annotated[
        Path,
        typer.Option("--seeds", help="Ruta al archivo YAML de semillas defectuosas."),
    ] = Path("specs/seeds_defective.yaml"),
    include_seeds: Annotated[
        bool,
        typer.Option(
            "--include-seeds/--no-seeds",
            help="Incluye las semillas defectuosas en el denominador generado.",
        ),
    ] = True,
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio raíz del paquete bajo estudio."),
    ] = Path("reference"),
    catalog: Annotated[
        Path,
        typer.Option("--catalog", "-c", help="Ruta al catálogo YAML de mutantes."),
    ] = DEFAULT_CATALOG_PATH,
    scan_target: Annotated[
        list[Path] | None,
        typer.Option("--scan-target", help="Rutas para análisis estático (repetible)."),
    ] = None,
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = Path("out"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help=f"Archivo de configuración [default: {DEFAULT_CONFIG_FILE}]"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="Segundos máximos de pytest; sustituye a codeguard.toml."),
    ] = None,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Semilla de reproducibilidad registrada en run_config.json."),
    ] = DEFAULT_SEED,
) -> None:
    """Reproduce el pipeline completo (generate->validate->run->mutate->scan->report)."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        timeout_seconds, import_timeout_seconds = _resolve_timeouts(config, timeout)
        options = PipelineOptions(
            run_id=resolved_run_id,
            specs_path=specs,
            seeds_path=seeds,
            include_seeds=include_seeds,
            reference_dir=reference_dir,
            catalog_path=catalog,
            scan_targets=tuple(scan_target) if scan_target else DEFAULT_SCAN_TARGETS,
            out_dir=out,
            timeout_seconds=timeout_seconds,
            seed=seed,
            import_timeout_seconds=import_timeout_seconds,
        )
        result = RunPipeline().execute(options)
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error en pipeline: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Pipeline completo (run_id={result.run_id}): "
        f"{result.proposals_valid}/{result.proposals_total} válidas | "
        f"{result.baseline_passed} pruebas base OK | "
        f"{_coverage_text(result.line_coverage_pct, result.branch_coverage_pct)} | "
        f"{result.mutants_killed}/{result.mutants_total} mutantes detectados | "
        f"{result.findings_total} hallazgos estáticos | "
        f"run_config: {result.run_config_path}"
    )


def _coverage_text(line_pct: float | None, branch_pct: float | None) -> str:
    if line_pct is None or branch_pct is None:
        return "cobertura no disponible"
    return f"cobertura {line_pct:.1f} % líneas / {branch_pct:.1f} % ramas"
