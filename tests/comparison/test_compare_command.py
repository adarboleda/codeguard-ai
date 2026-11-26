"""CLI tests for ``codeguard compare`` (CG-33)."""

import json
from pathlib import Path

from run_factory import make_run
from scenarios import MUTANTS_TEMPLATES, TEMPLATE, groq_run, templates_run
from typer.testing import CliRunner, Result

from codeguard.cli.main import app

runner = CliRunner()


def _compare(out: Path, *extra: str, templates: str = "tpl", groq: str = "gq") -> Result:
    return runner.invoke(
        app, ["compare", "--templates", templates, "--groq", groq, "--out", str(out), *extra]
    )


def test_compare_writes_the_table_and_prints_both_summaries(tmp_path: Path) -> None:
    templates_run(tmp_path)
    groq_run(tmp_path)

    result = _compare(tmp_path)

    assert result.exit_code == 0, result.output
    assert "Plantillas (tpl): 4/6 válidas (66.7 %) | mutantes 3/3 (100.0 %)" in result.output
    assert "Groq (gq): 3/5 válidas (60.0 %) | mutantes 2/3 (66.7 %)" in result.output
    markdown = (tmp_path / "comparison" / "comparison.md").read_text(encoding="utf-8")
    assert "**SURVIVED**" in markdown
    data = json.loads((tmp_path / "comparison" / "comparison.json").read_text(encoding="utf-8"))
    assert [source["label"] for source in data["sources"]] == ["Plantillas", "Groq"]


def test_dest_option_chooses_the_output_folder(tmp_path: Path) -> None:
    templates_run(tmp_path)
    groq_run(tmp_path)
    dest = tmp_path / "elsewhere"

    result = _compare(tmp_path, "--dest", str(dest))

    assert result.exit_code == 0, result.output
    assert (dest / "comparison.md").is_file()
    assert not (tmp_path / "comparison").exists()


def test_comparison_is_reproducible(tmp_path: Path) -> None:
    templates_run(tmp_path)
    groq_run(tmp_path)

    _compare(tmp_path)
    first = (tmp_path / "comparison" / "comparison.md").read_text(encoding="utf-8")
    _compare(tmp_path)

    assert (tmp_path / "comparison" / "comparison.md").read_text(encoding="utf-8") == first


def test_unfinished_run_says_what_to_run(tmp_path: Path) -> None:
    templates_run(tmp_path)

    result = _compare(tmp_path, groq="never-ran")

    assert result.exit_code == 1
    assert "Error de comparación: run directory not found" in result.output


def test_runs_with_different_mutants_are_refused(tmp_path: Path) -> None:
    templates_run(tmp_path)
    make_run(
        tmp_path,
        "gq",
        proposals=[("a", TEMPLATE, "weighted_mean", None), ("b", TEMPLATE, "clamp", None)],
        passed=2,
        mutants={"M01": ("weighted_mean", "KILLED")},
    )

    result = _compare(tmp_path)

    assert result.exit_code == 1
    assert "not comparable: different mutants" in result.output
    assert not (tmp_path / "comparison").exists()


def test_invalid_run_id_is_refused(tmp_path: Path) -> None:
    result = _compare(tmp_path, templates="../x")

    assert result.exit_code == 1
    assert "Invalid run_id" in result.output


def test_same_mutants_but_a_changed_catalog_entry_is_still_comparable(tmp_path: Path) -> None:
    """Only the ids must match: a status that differs between sources is the point."""
    templates_run(tmp_path)
    make_run(
        tmp_path,
        "gq",
        proposals=[("a", TEMPLATE, "weighted_mean", None), ("b", TEMPLATE, "clamp", None)],
        passed=2,
        mutants={**MUTANTS_TEMPLATES, "M01": ("weighted_mean", "SURVIVED")},
    )

    assert _compare(tmp_path).exit_code == 0
