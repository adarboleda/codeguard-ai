"""Use case: run the valid proposals of a run with pytest (CG-16).

Only proposals marked ``valid`` in the ledger are executed: rejected proposals
(e.g. the defective seeds) and any stray file in the proposals folder are never run.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from codeguard.domain.execution import SuiteResult
from codeguard.domain.ledger import LedgerEntry, ProposalStatus
from codeguard.ports.execution import SuiteRunner
from codeguard.ports.ledger import LedgerRepository


@dataclass(frozen=True)
class ExecutionReport:
    """Result of running the validated suite of one run."""

    result: SuiteResult
    test_files: tuple[Path, ...]


class RunSuite:
    """Selects the valid proposals from the ledger and runs them."""

    def __init__(self, runner: SuiteRunner, ledger: LedgerRepository) -> None:
        self._runner = runner
        self._ledger = ledger

    def execute(
        self, ledger_path: Path, proposals_dir: Path, package_root: Path, output_dir: Path
    ) -> ExecutionReport:
        """Run every valid proposal against ``package_root``; write results to ``output_dir``."""
        test_files = valid_test_files(self._ledger.read(ledger_path), proposals_dir)
        result = self._runner.run(test_files, package_root, output_dir)
        return ExecutionReport(result=result, test_files=test_files)


def valid_test_files(entries: Sequence[LedgerEntry], proposals_dir: Path) -> tuple[Path, ...]:
    """Paths of the proposals the validator accepted, in ledger order."""
    valid = [entry for entry in entries if entry.status is ProposalStatus.VALID]
    if not valid:
        raise ValueError("the ledger has no valid proposals; run 'codeguard validate' first")
    return tuple(proposals_dir / entry.file_name for entry in valid)
