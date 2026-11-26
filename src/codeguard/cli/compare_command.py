"""``codeguard compare``: plantillas vs. Groq sobre las mismas funciones y mutantes (CG-33)."""

from pathlib import Path
from typing import Annotated

import typer

from codeguard.adapters.reporting.comparison_writer import write_comparison
from codeguard.application.compare_sources import compare_runs
from codeguard.cli.run_command import _run_dir
from codeguard.domain.comparison import SourceSummary
from codeguard.domain.errors import CodeGuardError

TEMPLATES_LABEL = "Plantillas"
GROQ_LABEL = "Groq"


def compare_command(
    templates: Annotated[
        str,
        typer.Option("--templates", help="run_id de la corrida con plantillas (codeguard all)."),
    ],
    groq: Annotated[
        str,
        typer.Option(
            "--groq",
            help="run_id de la corrida con Groq (generate --source groq, validate, run, mutate).",
        ),
    ],
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Directorio raíz de salidas (out/).")
    ] = Path("out"),
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Carpeta de salida [default: <out>/comparison]."),
    ] = None,
) -> None:
    """Compara las dos fuentes y escribe comparison.md y comparison.json."""
    try:
        report = compare_runs(
            [(TEMPLATES_LABEL, _run_dir(out, templates)), (GROQ_LABEL, _run_dir(out, groq))]
        )
        markdown, data = write_comparison(report, dest or out / "comparison")
    except (CodeGuardError, ValueError) as error:
        typer.echo(f"Error de comparación: {error}", err=True)
        raise typer.Exit(code=1) from error
    for source in report.sources:
        typer.echo(_summary_line(source))
    typer.echo(f"Tabla: {markdown} | datos: {data}")


def _summary_line(source: SourceSummary) -> str:
    validity = "—" if source.validity_pct is None else f"{source.validity_pct:.1f} %"
    score = "—" if source.mutation_score_pct is None else f"{source.mutation_score_pct:.1f} %"
    return (
        f"{source.label} ({source.run_id}): {source.proposals_valid}/{source.proposals_total} "
        f"válidas ({validity}) | mutantes {source.killed}/{source.mutation_denominator} ({score})"
    )
