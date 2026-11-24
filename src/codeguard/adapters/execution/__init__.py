"""Suite execution (adapter of the ``SuiteRunner`` port)."""

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
    "DEFAULT_TIMEOUT_SECONDS",
    "JUNIT_FILE_NAME",
    "SCIREF_DIGEST_FILE_NAME",
    "SCIREF_PACKAGE_NAME",
    "PytestSubprocessRunner",
    "ScirefSnapshot",
    "compute_sciref_snapshot",
    "parse_junit",
    "verify_sciref_integrity",
]
