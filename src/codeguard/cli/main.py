"""Typer CLI entrypoint for CodeGuard AI."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from codeguard.adapters.specs import YamlSpecRepository
from codeguard.application.list_specs import ListContracts
from codeguard.domain import CaseKind, ContractCase, FunctionContract, SpecError

DEFAULT_SPECS_PATH = Path("specs/contracts.yaml")
DEFAULT_REFERENCE_DIR = Path("reference")

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
