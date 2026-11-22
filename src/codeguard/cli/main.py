"""Typer CLI entrypoint for CodeGuard AI."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from codeguard.adapters.generation import (
    CompositeProposalSource,
    DefectiveSeedProposalSource,
    FileProposalReader,
    FileProposalWriter,
    TemplateProposalSource,
)
from codeguard.adapters.ledger import JsonlLedger
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.adapters.validation import AssertionRule, ImportRule, SyntaxRule, TargetRule
from codeguard.application.generate_tests import GenerateTests
from codeguard.application.list_specs import ListContracts
from codeguard.application.validate_proposals import ValidateProposals
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import CaseKind, ContractCase, FunctionContract, SpecError
from codeguard.ports.generation import ProposalSource

DEFAULT_SPECS_PATH = Path("specs/contracts.yaml")
DEFAULT_SEEDS_PATH = Path("specs/seeds_defective.yaml")
DEFAULT_REFERENCE_DIR = Path("reference")
DEFAULT_OUT_DIR = Path("out")

app = typer.Typer(
    name="codeguard",
    help="CodeGuard AI: genera, filtra y evalúa pruebas pytest desde contratos YAML.",
    no_args_is_help=True,
)


def _configure_console_encoding() -> None:
    """Ensure UTF-8-safe output on Windows terminals without breaking test runners."""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None) or ""
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding.lower() != "utf-8" and callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _format_case_line(case: ContractCase) -> str:
    outcome = (
        f"raises {case.expected_exception}"
        if case.expects_exception
        else f"expected={case.expected!r}"
    )
    return f"      - {case.case_id} [{case.kind.value}] {outcome} | {case.description}"


def _format_contract_block(index: int, contract: FunctionContract) -> list[str]:
    summary = contract.docstring.splitlines()[0]
    counts = {
        kind: sum(1 for case in contract.cases if case.kind is kind)
        for kind in (CaseKind.NORMAL, CaseKind.BOUNDARY, CaseKind.INVALID)
    }
    lines = [
        f"[{index}] {contract.qualified_name} — {contract.signature}",
        f"    Contrato: {summary}",
        (
            f"    Casos ({len(contract.cases)}): "
            f"normal={counts[CaseKind.NORMAL]}, "
            f"frontera={counts[CaseKind.BOUNDARY]}, "
            f"invalido={counts[CaseKind.INVALID]}"
        ),
    ]
    lines.extend(_format_case_line(case) for case in contract.cases)
    return lines


@app.callback()
def main() -> None:
    """CodeGuard AI CLI."""
    _configure_console_encoding()


@app.command("list")
def list_contracts(
    specs: Annotated[
        Path,
        typer.Option("--specs", "-s", help="Ruta al archivo YAML de contratos."),
    ] = DEFAULT_SPECS_PATH,
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio raíz del paquete bajo estudio."),
    ] = DEFAULT_REFERENCE_DIR,
) -> None:
    """Carga, valida y muestra las funciones y casos definidos en contracts.yaml."""
    repository = YamlSpecRepository(specs_path=specs, search_paths=[reference_dir])
    try:
        contracts = ListContracts(repository).execute()
    except SpecError as error:
        typer.echo(f"Error de especificación: {error}", err=True)
        raise typer.Exit(code=1) from error

    total_cases = sum(len(contract.cases) for contract in contracts)
    typer.echo(f"Contratos cargados: {len(contracts)} funciones, {total_cases} casos")
    for index, contract in enumerate(contracts, start=1):
        typer.echo("")
        for line in _format_contract_block(index, contract):
            typer.echo(line)


def _resolve_run_id(run_id: str | None) -> str:
    if run_id is None:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    cleaned = run_id.strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid run_id {run_id!r}: must be a single non-empty directory name")
    return cleaned


def _build_proposal_source(seeds: Path, include_seeds: bool) -> ProposalSource:
    template_source = TemplateProposalSource()
    if not include_seeds:
        return template_source
    return CompositeProposalSource([template_source, DefectiveSeedProposalSource(seeds)])


@app.command("generate")
def generate_tests(
    specs: Annotated[
        Path,
        typer.Option("--specs", "-s", help="Ruta al archivo YAML de contratos."),
    ] = DEFAULT_SPECS_PATH,
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio raíz del paquete bajo estudio."),
    ] = DEFAULT_REFERENCE_DIR,
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = DEFAULT_OUT_DIR,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Identificador de corrida; por defecto marca temporal UTC."),
    ] = None,
    seeds: Annotated[
        Path,
        typer.Option("--seeds", help="Ruta al archivo YAML de semillas defectuosas."),
    ] = DEFAULT_SEEDS_PATH,
    include_seeds: Annotated[
        bool,
        typer.Option(
            "--include-seeds/--no-seeds",
            help="Incluye las semillas defectuosas en el denominador generado.",
        ),
    ] = True,
) -> None:
    """Genera pruebas pytest desde plantillas Jinja2 en out/<run_id>/proposals/."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        repository = YamlSpecRepository(specs_path=specs, search_paths=[reference_dir])
        source = _build_proposal_source(seeds, include_seeds)
        writer = FileProposalWriter()
        report = GenerateTests(repository, source, writer).execute(out / resolved_run_id)
    except SpecError as error:
        typer.echo(f"Error de especificación: {error}", err=True)
        raise typer.Exit(code=1) from error
    except ValueError as error:
        typer.echo(f"Error de generación: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Propuestas generadas: {len(report.proposals)} archivos "
        f"(run_id={resolved_run_id}) en {report.proposals_dir}"
    )


def _build_validation_chain(
    contracts: tuple[FunctionContract, ...],
    reference_dir: Path,
) -> ValidationChain:
    return ValidationChain(
        [
            SyntaxRule(),
            ImportRule(search_paths=[reference_dir]),
            TargetRule(contracts),
            AssertionRule(),
        ]
    )


@app.command("validate")
def validate_proposals(
    run_id: Annotated[
        str,
        typer.Option("--run-id", help="Identificador de corrida generado previamente."),
    ],
    specs: Annotated[
        Path,
        typer.Option("--specs", "-s", help="Ruta al archivo YAML de contratos."),
    ] = DEFAULT_SPECS_PATH,
    reference_dir: Annotated[
        Path,
        typer.Option("--reference-dir", "-r", help="Directorio raíz del paquete bajo estudio."),
    ] = DEFAULT_REFERENCE_DIR,
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Directorio raíz de salidas (out/)."),
    ] = DEFAULT_OUT_DIR,
) -> None:
    """Valida las propuestas generadas en out/<run_id>/proposals/ y escribe ledger.jsonl."""
    try:
        resolved_run_id = _resolve_run_id(run_id)
        run_dir = out / resolved_run_id
        contracts = YamlSpecRepository(specs_path=specs, search_paths=[reference_dir]).load()
        proposals = FileProposalReader().read(run_dir / "proposals")
        chain = _build_validation_chain(contracts, reference_dir)
        report = ValidateProposals(chain, JsonlLedger()).execute(proposals, run_dir)
    except SpecError as error:
        typer.echo(f"Error de especificación: {error}", err=True)
        raise typer.Exit(code=1) from error
    except ValueError as error:
        typer.echo(f"Error de validación: {error}", err=True)
        raise typer.Exit(code=1) from error

    summary = report.summary
    reasons = ", ".join(f"{reason}={count}" for reason, count in summary.by_reason.items())
    typer.echo(
        f"Validación completada: {summary.valid}/{summary.total} válidas "
        f"({summary.validity_pct:.1f}%), {summary.rejected} rechazadas "
        f"[motivos: {reasons or 'ninguno'}] | ledger: {report.ledger_path}"
    )
