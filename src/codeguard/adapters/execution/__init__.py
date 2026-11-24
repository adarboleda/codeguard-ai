"""Suite execution (adapter of the ``SuiteRunner`` port)."""

from .coverage import COVERAGE_HTML_DIR_NAME, COVERAGE_JSON_FILE_NAME, parse_coverage_json
from .integrity import (
    SCIREF_DIGEST_FILE_NAME,
    SCIREF_PACKAGE_NAME,
    ScirefSnapshot,
    compute_sciref_snapshot,
    verify_sciref_integrity,
)
from .junit import parse_junit
from .pytest_runner import DEFAULT_TIMEOUT_SECONDS, JUNIT_FILE_NAME, PytestSubprocessRunner

__all__ = [
    "COVERAGE_HTML_DIR_NAME",
    "COVERAGE_JSON_FILE_NAME",
    "DEFAULT_TIMEOUT_SECONDS",
    "JUNIT_FILE_NAME",
    "SCIREF_DIGEST_FILE_NAME",
    "SCIREF_PACKAGE_NAME",
    "PytestSubprocessRunner",
    "ScirefSnapshot",
    "compute_sciref_snapshot",
    "parse_coverage_json",
    "parse_junit",
    "verify_sciref_integrity",
]
