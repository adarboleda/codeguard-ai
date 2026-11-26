"""Tests for loading run artifacts into a comparison (CG-33)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from run_factory import MODEL, make_run
from scenarios import GROQ, TEMPLATE, groq_run, templates_run

from codeguard.application.compare_sources import compare_runs, load_source_summary


def test_templates_run_is_summarised_with_its_denominators(tmp_path: Path) -> None:
    source = load_source_summary("Plantillas", templates_run(tmp_path))

    assert (source.label, source.run_id) == ("Plantillas", "tpl")
    assert (source.proposals_total, source.proposals_valid) == (6, 4)
    assert (source.seeds_total, source.seeds_valid) == (2, 0)
    assert source.validity_pct == pytest.approx(100 * 4 / 6)
    assert source.validity_without_seeds_pct == pytest.approx(100.0)
    assert dict(source.rejected_by_reason) == {"SYNTAX_ERROR": 1, "TAUTOLOGICAL_ASSERTION": 1}
    assert {name: (c.total, c.valid) for name, c in source.per_function.items()} == {
        "weighted_mean": (3, 2),
        "clamp": (3, 2),
    }
    assert (source.tests_passed, source.tests_failed, source.tests_errors) == (4, 0, 0)
    assert (source.line_pct, source.branch_pct) == (100.0, 100.0)
    assert source.mutants_with("KILLED") == ("M01", "M02", "M04")
    assert source.mutation_score_pct == pytest.approx(100.0)
    assert dict(source.settings) == {"source": "template", "seed": "42"}


def test_groq_run_records_model_tokens_and_failed_calls(tmp_path: Path) -> None:
    source = load_source_summary("Groq", groq_run(tmp_path))

    assert (source.proposals_total, source.proposals_valid, source.seeds_total) == (5, 3, 0)
    assert dict(source.rejected_by_reason) == {"GENERATION_ERROR": 1, "WRONG_EXPECTATION": 1}
    assert (source.line_pct, source.branch_pct) == (
        pytest.approx(98.148, abs=1e-3),
        pytest.approx(96.667, abs=1e-3),
    )
    assert source.mutants_with("SURVIVED") == ("M02",)
    assert source.mutation_score_pct == pytest.approx(100 * 2 / 3)
    assert dict(source.settings) == {
        "source": "groq",
        "model": MODEL,
        "temperature": "0.0",
        "endpoint": "https://api.groq.com/openai/v1",
        "calls": "2",
        "failed_calls": "1",
        "tokens": "1000",
        "date_utc": datetime.now(UTC).date().isoformat(),
    }


def test_replayed_run_names_its_origin(tmp_path: Path) -> None:
    source = load_source_summary("Groq", groq_run(tmp_path, "gq2", replayed_from="gq"))

    assert source.settings["replayed_from"] == "gq"


def test_failed_tests_are_counted(tmp_path: Path) -> None:
    run = make_run(
        tmp_path,
        "r",
        proposals=[("a", GROQ, "clamp", None)],
        passed=2,
        failed=1,
        mutants={"M1": ("clamp", "KILLED")},
    )

    source = load_source_summary("X", run)

    assert (source.tests_passed, source.tests_failed) == (2, 1)
    assert (source.line_pct, source.branch_pct) == (None, None)  # no coverage.json


def test_compare_runs_builds_a_report(tmp_path: Path) -> None:
    report = compare_runs([("Plantillas", templates_run(tmp_path)), ("Groq", groq_run(tmp_path))])

    assert [source.label for source in report.sources] == ["Plantillas", "Groq"]
    assert report.functions == ("weighted_mean", "clamp")
    assert report.mutant_ids == ("M01", "M02", "M03", "M04")


def test_runs_with_different_mutants_are_not_compared(tmp_path: Path) -> None:
    other = make_run(
        tmp_path,
        "other",
        proposals=[("a", TEMPLATE, "weighted_mean", None), ("b", TEMPLATE, "clamp", None)],
        passed=2,
        mutants={"M01": ("weighted_mean", "KILLED")},
    )

    with pytest.raises(ValueError, match="not comparable: different mutants"):
        compare_runs([("A", templates_run(tmp_path)), ("B", other)])


def test_missing_run_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run directory not found"):
        load_source_summary("A", tmp_path / "nowhere")


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("ledger.jsonl", "ledger not found.*codeguard validate"),
        ("junit.xml", r"junit.xml not found in .*codeguard run"),
        ("mutants.json", r"mutants.json not found in .*codeguard mutate"),
    ],
)
def test_incomplete_run_says_which_command_to_run(
    tmp_path: Path, missing: str, message: str
) -> None:
    run = templates_run(tmp_path)
    (run / missing).unlink()

    with pytest.raises(ValueError, match=message):
        load_source_summary("A", run)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "cannot read"),
        ('{"mutant_id": "M1"}', "must be a JSON array"),
        ("[1]", "must be a JSON object"),
        ('[{"mutant_id": "M1", "status": "KILLED"}]', "need string mutant_id, status and function"),
    ],
)
def test_malformed_mutants_file(tmp_path: Path, content: str, message: str) -> None:
    run = templates_run(tmp_path)
    (run / "mutants.json").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_source_summary("A", run)


def test_unreadable_llm_records_are_ignored_when_not_objects(tmp_path: Path) -> None:
    run = templates_run(tmp_path)
    (run / "llm").mkdir()
    (run / "llm" / "x.json").write_text(json.dumps([1, 2]), encoding="utf-8")

    assert load_source_summary("A", run).settings["source"] == "template"
