"""Parse the JUnit XML written by ``pytest --junitxml`` (``junit_family = xunit1``)."""

import xml.etree.ElementTree as ET  # input is produced by our own pytest run
from pathlib import Path, PurePosixPath

from codeguard.domain.execution import ExecutedTest, ExecutionOutcome

_MAX_MESSAGE_CHARS = 300
_OUTCOME_TAGS = (
    ("failure", ExecutionOutcome.FAILED),
    ("error", ExecutionOutcome.ERROR),
    ("skipped", ExecutionOutcome.SKIPPED),
)


def parse_junit(path: Path) -> tuple[ExecutedTest, ...]:
    """Return one ``ExecutedTest`` per ``<testcase>``, in report order."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError(f"invalid JUnit XML {path}: {error}") from error
    return tuple(_executed_test(case) for case in root.iter("testcase"))


def _executed_test(case: ET.Element) -> ExecutedTest:
    outcome, message = ExecutionOutcome.PASSED, ""
    for tag, tag_outcome in _OUTCOME_TAGS:
        element = case.find(tag)
        if element is not None:
            outcome = tag_outcome
            message = (element.get("message") or "").strip()[:_MAX_MESSAGE_CHARS]
            break
    file_path = case.get("file", "").replace("\\", "/")  # Windows writes tests\test_x.py
    return ExecutedTest(
        node_id=_node_id(file_path, case.get("classname", ""), case.get("name", "")),
        file_name=PurePosixPath(file_path).name,
        outcome=outcome,
        duration_seconds=max(0.0, float(case.get("time") or 0.0)),
        message=message,
    )


def _node_id(file_path: str, classname: str, name: str) -> str:
    """Build a pytest-style id: ``tests/test_x.py::TestClass::test_y``."""
    if not file_path:
        return f"{classname}::{name}" if classname else name
    module = file_path.removesuffix(".py").replace("/", ".")
    parts = [file_path]
    if classname.startswith(f"{module}."):
        parts.append(classname.removeprefix(f"{module}.").replace(".", "::"))
    parts.append(name)
    return "::".join(parts)
