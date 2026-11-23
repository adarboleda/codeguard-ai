"""Port for running a test suite against a copy of the package under study."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from codeguard.domain.execution import SuiteResult


class SuiteRunner(Protocol):
    """Runs test files against the package found in ``package_root``.

    ``package_root`` is the directory that *contains* the package (``reference/`` for
    the original ``sciref``, or the temporary directory of a mutant). Implementations
    must never write into ``package_root``. Results are written under ``output_dir``.
    """

    def run(self, test_files: Sequence[Path], package_root: Path, output_dir: Path) -> SuiteResult:
        """Run the tests and return one result per executed test."""
        ...
