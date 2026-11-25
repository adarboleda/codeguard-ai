"""Tests for the Jinja2 HTML report renderer and ``codeguard report`` HTML output."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeguard.adapters.ledger import JsonlLedger
from codeguard.adapters.reporting import REPORT_HTML_FILE_NAME, JinjaHtmlReportRenderer
from codeguard.cli.main import app
from codeguard.domain import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.ledger import LedgerEntry

runner = CliRunner()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sample_entries() -> list[LedgerEntry]:
    code = (
        "from sciref.numeric import clamp\n\ndef test_cl_01():\n    assert clamp(5, 0, 10) == 5\n"
    )
    valid_proposal = TestProposal(
        proposal_id="tpl-clamp-cl_01",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code=code,
        case_ids=("CL-01",),
        file_name="test_clamp_cl_01.py",
    )
    bad_proposal = TestProposal(
        proposal_id="SEED-SYNTAX-01",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.DEFECTIVE_SEED,
        code="def broken(:\n",
        case_ids=("SEED-01",),
        file_name="test_seed_syntax.py",
    )
    return [
        LedgerEntry.from_validation(
            valid_proposal,
            ValidationVerdict("tpl-clamp-cl_01", valid=True),
        ),
        LedgerEntry.from_validation(
            bad_proposal,
            ValidationVerdict(
                "SEED-SYNTAX-01",
                valid=False,
                reason=RejectionReason.SYNTAX_ERROR,
                detail="invalid syntax",
                rule_name="syntax",
            ),
        ),
    ]


def _populate_full_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": run_dir.name,
            "seed": 42,
            "sciref_sha256": {"combined": "a" * 64, "files": {"sciref/numeric.py": "b" * 64}},
            "phase_durations_seconds": {"generate": 0.1, "validate": 0.5, "run": 1.2},
        },
    )
    JsonlLedger().write(_sample_entries(), run_dir)
    (run_dir / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuite name="pytest" tests="2" errors="0" failures="1" skipped="0" time="0.25">'
        '<testcase classname="tests.test_clamp_cl_01" name="test_cl_01" time="0.05"/>'
        '<testcase classname="tests.test_clamp_cl_02" name="test_cl_02" time="0.20">'
        '<failure message="AssertionError">assert 1 == 2</failure>'
        "</testcase>"
        "</testsuite>\n",
        encoding="utf-8",
    )
    _write_json(
        run_dir / "coverage.json",
        {
            "files": {
                "sciref/numeric.py": {
                    "summary": {
                        "num_statements": 20,
                        "covered_lines": 18,
                        "num_branches": 8,
                        "covered_branches": 7,
                    },
                    "missing_lines": [12, 19],
                }
            }
        },
    )
    (run_dir / "coverage_html").mkdir()
    (run_dir / "coverage_html" / "index.html").write_text("<html/>", encoding="utf-8")
    _write_json(
        run_dir / "mutants.json",
        [
            {
                "mutant_id": "M01",
                "function": "clamp",
                "status": "KILLED",
                "exit_code": 1,
                "timed_out": False,
                "failed": 2,
                "duration_seconds": 0.8,
            },
            {
                "mutant_id": "M02",
                "function": "lerp",
                "status": "SURVIVED",
                "exit_code": 0,
                "timed_out": False,
                "failed": 0,
                "duration_seconds": 0.7,
            },
            {
                "mutant_id": "M03",
                "function": "clamp",
                "status": "EQUIVALENT",
                "exit_code": 0,
                "timed_out": False,
                "failed": 0,
                "duration_seconds": 0.6,
            },
        ],
    )
    _write_json(
        run_dir / "findings.json",
        [
            {
                "rule_id": "CG001",
                "severity": "HIGH",
                "file_path": "samples/security/vuln.py",
                "line": 10,
                "column": 4,
                "snippet": "eval(user_input)",
                "message": "Uso peligroso de eval()",
                "recommendation": "Use ast.literal_eval",
            },
            {
                "rule_id": "CG002",
                "severity": "MEDIUM",
                "file_path": "samples/security/vuln.py",
                "line": 22,
                "column": 0,
                "snippet": "subprocess.run(cmd, shell=True)",
                "message": "shell=True detectado",
                "recommendation": "Use lista de argumentos",
            },
        ],
    )


def test_render_full_report_contains_three_sections_and_data(tmp_path: Path) -> None:
    run_dir = tmp_path / "full-run"
    _populate_full_run(run_dir)

    result = JinjaHtmlReportRenderer().render_run(run_dir)

    assert result.run_id == "full-run"
    assert result.report_path == run_dir / REPORT_HTML_FILE_NAME
    html = result.report_path.read_text(encoding="utf-8")

    # Three distinct top-level sections in exact order
    sec_func = html.index('<section id="functional-tests">')
    sec_mut = html.index('<section id="mutation-analysis">')
    sec_stat = html.index('<section id="static-analysis">')
    assert sec_func < sec_mut < sec_stat

    # Section 1: ledger, JUnit results, coverage
    assert "tpl-clamp-cl_01" in html
    assert "SEED-SYNTAX-01" in html
    assert "50.00%" in html
    assert "tests.test_clamp_cl_02::test_cl_02" in html
    assert "sciref/numeric.py" in html
    assert "90.00%" in html
    assert "87.50%" in html
    assert "coverage_html/index.html" in html

    # Section 2: mutation
    assert "M01" in html
    assert "M02" in html
    assert "M03" in html
    assert "EQUIVALENT" in html
    assert "1 / 2" in html

    # Section 3: static findings
    assert "CG001" in html
    assert "CG002" in html
    assert "eval(user_input)" in html
    assert "subprocess.run(cmd, shell=True)" in html


def test_render_partial_run_handles_missing_artifacts_gracefully(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()

    result = JinjaHtmlReportRenderer().render_run(run_dir)
    html = result.report_path.read_text(encoding="utf-8")

    assert 'id="functional-tests"' in html
    assert 'id="mutation-analysis"' in html
    assert 'id="static-analysis"' in html
    assert "ledger.jsonl" in html
    assert "junit.xml" in html
    assert "coverage.json" in html
    assert "mutants.json" in html
    assert "findings.json" in html


def test_render_escapes_html_in_snippets_and_details(tmp_path: Path) -> None:
    run_dir = tmp_path / "xss-run"
    run_dir.mkdir()
    xss = '<script>alert("xss")</script>'
    bad = TestProposal(
        proposal_id="P-XSS",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.DEFECTIVE_SEED,
        code="x = 1\n",
        file_name="test_xss.py",
    )
    entry = LedgerEntry.from_validation(
        bad,
        ValidationVerdict(
            "P-XSS",
            valid=False,
            reason=RejectionReason.SYNTAX_ERROR,
            detail=xss,
            rule_name="syntax",
        ),
    )
    JsonlLedger().write([entry], run_dir)
    _write_json(
        run_dir / "findings.json",
        [
            {
                "rule_id": "CG001",
                "severity": "HIGH",
                "file_path": "a.py",
                "line": 1,
                "column": 0,
                "snippet": xss,
                "message": "msg",
                "recommendation": "rec",
            }
        ],
    )

    result = JinjaHtmlReportRenderer().render_run(run_dir)
    html = result.report_path.read_text(encoding="utf-8")

    assert '<script>alert("xss")</script>' not in html
    assert "&lt;script&gt;" in html


def test_render_missing_run_dir_raises_value_error(tmp_path: Path) -> None:
    renderer = JinjaHtmlReportRenderer()
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ValueError, match="run directory not found"):
        renderer.render_run(missing)


def test_cli_report_command_generates_report_html(tmp_path: Path) -> None:
    run_dir = tmp_path / "cli-rep"
    _populate_full_run(run_dir)

    res = runner.invoke(app, ["report", "--run-id", "cli-rep", "--out", str(tmp_path)])

    assert res.exit_code == 0, res.output
    assert "report.html" in res.output
    report_path = run_dir / REPORT_HTML_FILE_NAME
    assert report_path.is_file()
    html = report_path.read_text(encoding="utf-8")
    assert 'id="functional-tests"' in html
    assert 'id="mutation-analysis"' in html
    assert 'id="static-analysis"' in html
