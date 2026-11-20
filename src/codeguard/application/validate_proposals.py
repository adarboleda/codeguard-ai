"""Use case: validate every proposal and record all of them in the ledger (CG-09..CG-12)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import TestProposal
from codeguard.domain.ledger import LedgerEntry, LedgerSummary
from codeguard.ports.ledger import LedgerRepository


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of validating a batch of proposals."""

    entries: tuple[LedgerEntry, ...]
    summary: LedgerSummary
    ledger_path: Path


class ValidateProposals:
    """Runs the validation chain and writes ``ledger.jsonl`` with every proposal."""

    def __init__(self, chain: ValidationChain, ledger: LedgerRepository) -> None:
        self._chain = chain
        self._ledger = ledger

    def execute(self, proposals: Sequence[TestProposal], run_dir: Path) -> ValidationReport:
        """Validate in order, keep rejected proposals, and persist the ledger."""
        _require_unique_ids(proposals)
        verdicts = self._chain.validate_all(proposals)
        entries = tuple(
            LedgerEntry.from_validation(proposal, verdict)
            for proposal, verdict in zip(proposals, verdicts, strict=True)
        )
        ledger_path = self._ledger.write(entries, run_dir)
        return ValidationReport(entries, LedgerSummary.from_entries(entries), ledger_path)


def _require_unique_ids(proposals: Sequence[TestProposal]) -> None:
    counts = Counter(proposal.proposal_id for proposal in proposals)
    duplicated = sorted(proposal_id for proposal_id, count in counts.items() if count > 1)
    if duplicated:
        raise ValueError(f"duplicate proposal_id in batch: {', '.join(duplicated)}")
