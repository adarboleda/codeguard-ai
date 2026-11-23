"""Tests for the RunSuite use case: only proposals validated in the ledger are executed."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from codeguard.adapters.ledger import JsonlLedger
from codeguard.application.run_suite import RunSuite
from codeguard.domain import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.execution import SuiteResult
from codeguard.domain.ledger import LedgerEntry


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Path, ...], Path, Path]] = []

    def run(self, test_files: Sequence[Path], package_root: Path, output_dir: Path) -> SuiteResult:
        self.calls.append((tuple(test_files), package_root, output_dir))
        return SuiteResult(tests=(), exit_code=0, duration_seconds=0.1)


def _entry(file_name: str, valid: bool) -> LedgerEntry:
    proposal = TestProposal(
        proposal_id=file_name.removesuffix(".py"),
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE if valid else ProposalSourceKind.DEFECTIVE_SEED,
        code="# code\n",
        file_name=file_name,
    )
    reason = None if valid else RejectionReason.SYNTAX_ERROR
    verdict = ValidationVerdict(proposal.proposal_id, valid, reason)
    return LedgerEntry.from_validation(proposal, verdict)


def test_only_valid_proposals_are_run_in_ledger_order(tmp_path: Path) -> None:
    ledger_path = JsonlLedger().write(
        [_entry("test_b.py", True), _entry("test_seed.py", False), _entry("test_a.py", True)],
        tmp_path,
    )
    runner = _RecordingRunner()

    report = RunSuite(runner, JsonlLedger()).execute(
        ledger_path, tmp_path / "proposals", Path("reference"), tmp_path
    )

    files, package_root, output_dir = runner.calls[0]
    assert [path.name for path in files] == ["test_b.py", "test_a.py"]
    assert files[0].parent == tmp_path / "proposals"
    assert (package_root, output_dir) == (Path("reference"), tmp_path)
    assert report.test_files == files


def test_ledger_without_valid_proposals_is_refused(tmp_path: Path) -> None:
    ledger_path = JsonlLedger().write([_entry("test_seed.py", False)], tmp_path)

    with pytest.raises(ValueError, match="no valid proposals"):
        RunSuite(_RecordingRunner(), JsonlLedger()).execute(
            ledger_path, tmp_path, Path("reference"), tmp_path
        )


def test_missing_ledger_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"ledger not found.*codeguard validate"):
        RunSuite(_RecordingRunner(), JsonlLedger()).execute(
            tmp_path / "ledger.jsonl", tmp_path, Path("reference"), tmp_path
        )
