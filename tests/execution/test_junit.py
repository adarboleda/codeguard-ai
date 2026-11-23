"""Tests for the JUnit XML parser (CG-16)."""

from pathlib import Path

import pytest

from codeguard.adapters.execution import parse_junit
from codeguard.domain.execution import ExecutionOutcome

REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="5" time="0.2">
  <testcase classname="tests.test_clamp_cl_01" name="test_clamp_cl_01"
            file="tests/test_clamp_cl_01.py" line="9" time="0.004"/>
  <testcase classname="tests.test_clamp_cl_02" name="test_clamp_cl_02"
            file="tests/test_clamp_cl_02.py" line="9" time="0.010">
    <failure message="assert 999.0 == 0.0">traceback...</failure>
  </testcase>
  <testcase classname="tests.test_wm" name="test_uses_fixture"
            file="tests/test_wm.py" line="3" time="0.001">
    <error message="fixture 'missing' not found">setup...</error>
  </testcase>
  <testcase classname="tests.test_wm.TestWeightedMean" name="test_basic"
            file="tests/test_wm.py" line="7" time="0.002">
    <skipped type="pytest.skip" message="not today">skip</skipped>
  </testcase>
  <testcase classname="" name="tests.test_broken" time="0.000">
    <error message="collection failure">SyntaxError</error>
  </testcase>
</testsuite></testsuites>
"""


@pytest.fixture
def report_path(tmp_path: Path) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text(REPORT, encoding="utf-8")
    return path


def test_outcomes_ids_and_times(report_path: Path) -> None:
    tests = parse_junit(report_path)

    assert [(t.node_id, t.outcome) for t in tests] == [
        ("tests/test_clamp_cl_01.py::test_clamp_cl_01", ExecutionOutcome.PASSED),
        ("tests/test_clamp_cl_02.py::test_clamp_cl_02", ExecutionOutcome.FAILED),
        ("tests/test_wm.py::test_uses_fixture", ExecutionOutcome.ERROR),
        ("tests/test_wm.py::TestWeightedMean::test_basic", ExecutionOutcome.SKIPPED),
        ("tests.test_broken", ExecutionOutcome.ERROR),
    ]
    assert tests[0].duration_seconds == pytest.approx(0.004)
    assert tests[0].message == ""


def test_messages_and_file_names(report_path: Path) -> None:
    tests = parse_junit(report_path)

    assert tests[1].message == "assert 999.0 == 0.0"
    assert tests[2].message == "fixture 'missing' not found"
    assert [t.file_name for t in tests] == [
        "test_clamp_cl_01.py",
        "test_clamp_cl_02.py",
        "test_wm.py",
        "test_wm.py",
        "",
    ]


def test_windows_file_paths_are_normalised(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuite><testcase classname="tests.test_x" name="test_y" '
        'file="tests\\test_x.py" time="0.1"/></testsuite>',
        encoding="utf-8",
    )

    (test,) = parse_junit(path)

    assert (test.node_id, test.file_name) == ("tests/test_x.py::test_y", "test_x.py")


def test_long_messages_are_truncated(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    long_message = "x" * 1000
    path.write_text(
        f'<testsuite><testcase classname="c" name="t" time="1">'
        f'<failure message="{long_message}"/></testcase></testsuite>',
        encoding="utf-8",
    )

    (test,) = parse_junit(path)

    assert len(test.message) == 300
    assert test.node_id == "c::t"


def test_invalid_xml_raises(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text("<testsuite><testcase", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JUnit XML"):
        parse_junit(path)
