"""Render the source comparison as Markdown (for the report) and JSON (for other tools).

The Markdown is written in Spanish, like the rest of the report: percentages use a decimal
comma and an explicit denominator ("95,8 % (46/48)"); ``—`` means "not applicable".
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from codeguard.domain.comparison import ComparisonReport, SourceSummary

COMPARISON_MD_FILE_NAME = "comparison.md"
COMPARISON_JSON_FILE_NAME = "comparison.json"
_NA = "—"

_SETTING_LABELS = (
    ("source", "Fuente"),
    ("model", "Modelo"),
    ("temperature", "Temperatura"),
    ("endpoint", "Endpoint"),
    ("calls", "Llamadas a la API"),
    ("failed_calls", "Llamadas fallidas"),
    ("tokens", "Tokens totales"),
    ("date_utc", "Fecha de las llamadas (UTC)"),
    ("replayed_from", "Reproducida desde"),
    ("seed", "Semilla"),
)
_SOURCE_NAMES = {
    "template": "Plantillas Jinja2 (deterministas)",
    "groq": "Groq (API compatible con OpenAI)",
}


def write_comparison(report: ComparisonReport, dest: Path) -> tuple[Path, Path]:
    """Write ``comparison.md`` and ``comparison.json`` into ``dest`` (created if needed)."""
    dest.mkdir(parents=True, exist_ok=True)
    markdown = dest / COMPARISON_MD_FILE_NAME
    markdown.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    data = dest / COMPARISON_JSON_FILE_NAME
    payload = json.dumps(to_dict(report), indent=2, ensure_ascii=False) + "\n"
    data.write_text(payload, encoding="utf-8", newline="\n")
    return markdown, data


def render_markdown(report: ComparisonReport) -> str:
    """The comparison tables, ready to paste into the report."""
    labels = [source.label for source in report.sources]
    runs = ", ".join(f"`{source.run_id}`" for source in report.sources)
    blocks = [
        f"# Comparación de fuentes de propuestas: {' vs. '.join(labels)}",
        f"Mismas {len(report.functions)} funciones de `sciref` y los mismos "
        f"{len(report.mutant_ids)} mutantes del catálogo. Corridas: {runs}.",
        "## Resumen",
        _table(["Indicador", *labels], _summary_rows(report.sources)),
        "## Motivos de rechazo",
        _table(["Motivo", *labels], _reason_rows(report.sources)),
        "## Por función",
        _table(
            [
                "Función",
                *[f"Propuestas válidas · {name}" for name in labels],
                *[f"Mutantes detectados · {name}" for name in labels],
            ],
            _function_rows(report),
        ),
        "## Mutante por mutante",
        _table(["Mutante", "Función", *labels], _mutant_rows(report)),
        "## Modelo y configuración registrados",
        _table(["Parámetro", *labels], _settings_rows(report.sources)),
        "Notas: la validez y las propuestas por función incluyen las semillas defectuosas "
        "(en el denominador); la tasa de mutación es detectados / (detectados + sobrevivientes) "
        "y deja aparte los mutantes equivalentes e inválidos; la cobertura es solo la de "
        "`sciref`.",
    ]
    return "\n\n".join(blocks) + "\n"


def to_dict(report: ComparisonReport) -> dict[str, object]:
    """JSON-serialisable form with every derived figure next to its raw counts."""
    return {"sources": [_source_dict(source) for source in report.sources]}


def _source_dict(source: SourceSummary) -> dict[str, object]:
    return {
        "label": source.label,
        "run_id": source.run_id,
        "proposals": {
            "total": source.proposals_total,
            "valid": source.proposals_valid,
            "defective_seeds": source.seeds_total,
            "validity_pct": source.validity_pct,
            "validity_without_seeds_pct": source.validity_without_seeds_pct,
            "rejected_by_reason": dict(source.rejected_by_reason),
            "per_function": {
                name: {"total": counts.total, "valid": counts.valid}
                for name, counts in source.per_function.items()
            },
        },
        "execution": {
            "passed": source.tests_passed,
            "failed": source.tests_failed,
            "errors": source.tests_errors,
        },
        "coverage": {"line_pct": source.line_pct, "branch_pct": source.branch_pct},
        "mutation": {
            "killed": source.killed,
            "survived": source.survived,
            "equivalent": source.equivalent,
            "invalid": source.invalid,
            "denominator": source.mutation_denominator,
            "score_pct": source.mutation_score_pct,
            "statuses": dict(source.mutants),
        },
        "settings": dict(source.settings),
    }


# ---------------------------------------------------------------- rows


def _summary_rows(sources: Sequence[SourceSummary]) -> list[list[str]]:
    def row(name: str, value: Callable[[SourceSummary], str]) -> list[str]:
        return [name, *[value(source) for source in sources]]

    return [
        row("Propuestas", lambda s: str(s.proposals_total)),
        row("Válidas", lambda s: str(s.proposals_valid)),
        row(
            "Validez (todas las propuestas)", lambda s: _ratio(s.proposals_valid, s.proposals_total)
        ),
        row(
            "Validez sin semillas defectuosas",
            lambda s: _ratio(s.proposals_valid - s.seeds_valid, s.proposals_total - s.seeds_total),
        ),
        row("Pruebas ejecutadas · aprobadas", lambda s: f"{_executed(s)} · {s.tests_passed}"),
        row("Cobertura de líneas", lambda s: _pct(s.line_pct)),
        row("Cobertura de ramas", lambda s: _pct(s.branch_pct)),
        row("Mutantes detectados", lambda s: _ratio(s.killed, s.mutation_denominator)),
        row("Mutantes sobrevivientes", lambda s: _ids(s.mutants_with("SURVIVED"))),
        row("Mutantes equivalentes", lambda s: _ids(s.mutants_with("EQUIVALENT"))),
        row("Mutantes inválidos", lambda s: _ids(s.mutants_with("INVALID"))),
    ]


def _reason_rows(sources: Sequence[SourceSummary]) -> list[list[str]]:
    reasons = sorted({reason for source in sources for reason in source.rejected_by_reason})
    if not reasons:
        return [["ninguno", *["0" for _ in sources]]]
    return [
        [reason, *[str(s.rejected_by_reason.get(reason, 0)) for s in sources]] for reason in reasons
    ]


def _function_rows(report: ComparisonReport) -> list[list[str]]:
    rows = []
    for function in report.functions:
        proposals = [
            f"{s.per_function[function].valid}/{s.per_function[function].total}"
            for s in report.sources
        ]
        mutants = [_killed_over(s.mutation_for_function(function)) for s in report.sources]
        rows.append([f"`{function}`", *proposals, *mutants])
    return rows


def _mutant_rows(report: ComparisonReport) -> list[list[str]]:
    first = report.sources[0]
    return [
        [
            mutant_id,
            f"`{first.mutant_functions[mutant_id]}`",
            *[_status(s, mutant_id) for s in report.sources],
        ]
        for mutant_id in report.mutant_ids
    ]


def _settings_rows(sources: Sequence[SourceSummary]) -> list[list[str]]:
    rows = []
    for key, label in _SETTING_LABELS:
        if not any(key in source.settings for source in sources):
            continue
        rows.append([label, *[_setting(source, key) for source in sources]])
    return rows


# ---------------------------------------------------------------- formatting


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *["| " + " | ".join(cells) + " |" for cells in rows],
    ]
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return _NA if value is None else f"{value:.1f}".replace(".", ",") + " %"


def _ratio(part: int, whole: int) -> str:
    return _NA if whole == 0 else f"{_pct(part / whole * 100)} ({part}/{whole})"


def _ids(ids: Sequence[str]) -> str:
    return ", ".join(ids) if ids else _NA


def _executed(source: SourceSummary) -> int:
    return source.tests_passed + source.tests_failed + source.tests_errors


def _killed_over(counts: tuple[int, int]) -> str:
    killed, valid = counts
    return f"{killed}/{valid}" if valid else _NA


def _status(source: SourceSummary, mutant_id: str) -> str:
    status = source.mutants[mutant_id]
    return f"**{status}**" if status == "SURVIVED" else status


def _setting(source: SourceSummary, key: str) -> str:
    value = source.settings.get(key)
    if not value:
        return _NA
    return _SOURCE_NAMES.get(value, value) if key == "source" else value
