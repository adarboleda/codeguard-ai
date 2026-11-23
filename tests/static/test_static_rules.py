"""Tests for the static rules CG001 and CG002 (CG-15)."""

from pathlib import Path

import pytest

from codeguard.adapters.static import registered_rules, scan_paths, scan_source
from codeguard.domain import Severity

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples" / "security"

INSECURE_EXPECTED = {
    "insecure_eval.py": "CG001",
    "insecure_exec.py": "CG001",
    "insecure_shell_true.py": "CG002",
    "insecure_os_system.py": "CG002",
}
SAFE_FILES = (
    "safe_eval_literal.py",
    "safe_exec_literal.py",
    "safe_subprocess_list.py",
    "safe_os_path.py",
)


def test_registry_contains_cg001_and_cg002() -> None:
    assert {rule.rule_id for rule in registered_rules()} == {"CG001", "CG002"}


@pytest.mark.parametrize(("file_name", "rule_id"), INSECURE_EXPECTED.items())
def test_insecure_example_is_flagged_once_by_expected_rule(file_name: str, rule_id: str) -> None:
    findings = scan_paths([SAMPLES / file_name])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == rule_id
    assert finding.severity is Severity.HIGH
    assert finding.line >= 1
    assert finding.snippet
    assert finding.recommendation
    assert finding.message


@pytest.mark.parametrize("file_name", SAFE_FILES)
def test_safe_example_is_not_flagged(file_name: str) -> None:
    assert scan_paths([SAMPLES / file_name]) == ()


def test_all_examples_together_give_exactly_four_findings() -> None:
    findings = scan_paths([SAMPLES])

    assert len(findings) == 4
    assert sorted(f.rule_id for f in findings) == ["CG001", "CG001", "CG002", "CG002"]


def test_finding_reports_the_line_and_snippet_of_the_call() -> None:
    source = "x = 1\ny = eval(payload)\n"

    (finding,) = scan_source(source, "demo.py")

    assert finding.line == 2
    assert finding.column == 4
    assert finding.snippet == "y = eval(payload)"


@pytest.mark.parametrize(
    "source",
    [
        "eval('1')",
        "eval(b'1')",
        "exec('x = 1')",
        "eval()",
        "print(eval)",
    ],
)
def test_cg001_ignores_literals_and_non_calls(source: str) -> None:
    assert scan_source(source, "t.py") == ()


def test_cg001_flags_non_literal_argument_even_when_nested() -> None:
    source = "def f(a):\n    return [eval(a) for _ in range(2)]\n"

    findings = scan_source(source, "t.py")

    assert [f.rule_id for f in findings] == ["CG001"]


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(cmd, shell=True)",
        "import subprocess\nsubprocess.Popen(cmd, shell=True)",
        "import subprocess\nsubprocess.check_output(['ls'], shell=True)",
        "import os\nos.system('ls')",
    ],
)
def test_cg002_flags_shell_execution(source: str) -> None:
    findings = scan_source(source, "t.py")

    assert [f.rule_id for f in findings] == ["CG002"]


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['ls'], shell=False)",
        "import subprocess\nsubprocess.run(['ls'])",
        "import subprocess\nsubprocess.run(cmd, shell=flag)",
        "import os\nos.getcwd()",
        "shell = True\nprint(shell)",
    ],
)
def test_cg002_ignores_safe_calls(source: str) -> None:
    assert scan_source(source, "t.py") == ()
