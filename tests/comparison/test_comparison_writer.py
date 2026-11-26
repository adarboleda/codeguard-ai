"""Tests for the Markdown and JSON rendering of the comparison (CG-33)."""

import json
from pathlib import Path

import pytest
from scenarios import groq_run, templates_run

from codeguard.adapters.reporting.comparison_writer import (
    render_markdown,
    to_dict,
    write_comparison,
)
from codeguard.application.compare_sources import compare_runs
from codeguard.domain.comparison import ComparisonReport


@pytest.fixture
def report(tmp_path: Path) -> ComparisonReport:
    return compare_runs([("Plantillas", templates_run(tmp_path)), ("Groq", groq_run(tmp_path))])


def _row(markdown: str, first_cell: str) -> list[str]:
    for line in markdown.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if line.startswith("|") and cells[0] == first_cell:
            return cells
    raise AssertionError(f"no row starting with {first_cell!r}")


def test_summary_table_shows_every_figure_with_its_denominator(report: ComparisonReport) -> None:
    markdown = render_markdown(report)

    assert markdown.startswith("# Comparación de fuentes de propuestas: Plantillas vs. Groq")
    assert "Mismas 2 funciones de `sciref` y los mismos 4 mutantes" in markdown
    assert _row(markdown, "Propuestas") == ["Propuestas", "6", "5"]
    assert _row(markdown, "Validez (todas las propuestas)")[1:] == ["66,7 % (4/6)", "60,0 % (3/5)"]
    assert _row(markdown, "Validez sin semillas defectuosas")[1:] == [
        "100,0 % (4/4)",
        "60,0 % (3/5)",
    ]
    assert _row(markdown, "Pruebas ejecutadas · aprobadas")[1:] == ["4 · 4", "3 · 3"]
    assert _row(markdown, "Cobertura de líneas")[1:] == ["100,0 %", "98,1 %"]
    assert _row(markdown, "Cobertura de ramas")[1:] == ["100,0 %", "96,7 %"]
    assert _row(markdown, "Mutantes detectados")[1:] == ["100,0 % (3/3)", "66,7 % (2/3)"]
    assert _row(markdown, "Mutantes sobrevivientes")[1:] == ["—", "M02"]
    assert _row(markdown, "Mutantes equivalentes")[1:] == ["M03", "M03"]
    assert _row(markdown, "Mutantes inválidos")[1:] == ["—", "—"]


def test_rejection_reasons_are_listed_for_both_sources(report: ComparisonReport) -> None:
    markdown = render_markdown(report)

    assert _row(markdown, "GENERATION_ERROR")[1:] == ["0", "1"]
    assert _row(markdown, "SYNTAX_ERROR")[1:] == ["1", "0"]
    assert _row(markdown, "TAUTOLOGICAL_ASSERTION")[1:] == ["1", "0"]
    assert _row(markdown, "WRONG_EXPECTATION")[1:] == ["0", "1"]


def test_per_function_and_per_mutant_tables(report: ComparisonReport) -> None:
    markdown = render_markdown(report)

    assert _row(markdown, "`weighted_mean`")[1:] == ["2/3", "2/3", "2/2", "1/2"]
    assert _row(markdown, "`clamp`")[1:] == ["2/3", "1/2", "1/1", "1/1"]
    assert _row(markdown, "M02") == ["M02", "`weighted_mean`", "KILLED", "**SURVIVED**"]
    assert _row(markdown, "M03")[2:] == ["EQUIVALENT", "EQUIVALENT"]


def test_settings_table_records_model_and_configuration(report: ComparisonReport) -> None:
    markdown = render_markdown(report)

    assert _row(markdown, "Fuente")[1:] == [
        "Plantillas Jinja2 (deterministas)",
        "Groq (API compatible con OpenAI)",
    ]
    assert _row(markdown, "Modelo")[1:] == ["—", "openai/gpt-oss-120b"]
    assert _row(markdown, "Temperatura")[1:] == ["—", "0.0"]
    assert _row(markdown, "Tokens totales")[1:] == ["—", "1000"]
    assert _row(markdown, "Llamadas fallidas")[1:] == ["—", "1"]
    assert _row(markdown, "Semilla")[1:] == ["42", "—"]
    assert "Reproducida desde" not in markdown  # no source was replayed


def test_no_rejections_is_stated(tmp_path: Path) -> None:
    from run_factory import make_run
    from scenarios import MUTANTS_TEMPLATES, TEMPLATE

    runs = [
        make_run(
            tmp_path,
            name,
            proposals=[("a", TEMPLATE, "weighted_mean", None), ("b", TEMPLATE, "clamp", None)],
            passed=2,
            mutants=MUTANTS_TEMPLATES,
        )
        for name in ("one", "two")
    ]

    markdown = render_markdown(compare_runs([("A", runs[0]), ("B", runs[1])]))

    assert _row(markdown, "ninguno")[1:] == ["0", "0"]
    assert _row(markdown, "Cobertura de líneas")[1:] == ["—", "—"]


def test_json_keeps_raw_counts_next_to_percentages(report: ComparisonReport) -> None:
    data = to_dict(report)

    groq = data["sources"][1]  # type: ignore[index]
    assert groq["label"] == "Groq"
    assert groq["proposals"]["total"] == 5
    assert groq["proposals"]["valid"] == 3
    assert groq["proposals"]["rejected_by_reason"] == {
        "GENERATION_ERROR": 1,
        "WRONG_EXPECTATION": 1,
    }
    assert groq["mutation"]["killed"] == 2
    assert groq["mutation"]["denominator"] == 3
    assert groq["mutation"]["statuses"]["M02"] == "SURVIVED"
    assert groq["settings"]["model"] == "openai/gpt-oss-120b"


def test_write_comparison_creates_both_files_with_lf(
    report: ComparisonReport, tmp_path: Path
) -> None:
    markdown, data = write_comparison(report, tmp_path / "nested" / "comparison")

    assert markdown.name == "comparison.md"
    assert data.name == "comparison.json"
    assert b"\r\n" not in markdown.read_bytes()
    assert markdown.read_text(encoding="utf-8") == render_markdown(report)
    assert json.loads(data.read_text(encoding="utf-8")) == json.loads(json.dumps(to_dict(report)))
