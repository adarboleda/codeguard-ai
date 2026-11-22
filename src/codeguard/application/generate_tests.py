"""Use case: generate test proposals from contracts and write them to disk (CG-07)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from codeguard.domain import TestProposal
from codeguard.ports.generation import ProposalSource, ProposalWriter
from codeguard.ports.specs import SpecRepository


@dataclass(frozen=True)
class GenerationReport:
    """Outcome of generating and persisting test proposals for a run."""

    proposals: tuple[TestProposal, ...]
    written_paths: tuple[Path, ...]
    proposals_dir: Path


class GenerateTests:
    """Loads contracts, generates proposals via ``ProposalSource``, and writes them."""

    def __init__(
        self,
        spec_repository: SpecRepository,
        proposal_source: ProposalSource,
        proposal_writer: ProposalWriter,
    ) -> None:
        self._spec_repository = spec_repository
        self._proposal_source = proposal_source
        self._proposal_writer = proposal_writer

    def execute(self, run_dir: Path) -> GenerationReport:
        """Load contracts, generate proposals, and write them to ``run_dir/proposals``."""
        contracts = self._spec_repository.load()
        proposals = self._proposal_source.generate(contracts)
        _require_unique_ids(proposals)
        proposals_dir = run_dir / "proposals"
        written_paths = self._proposal_writer.write(proposals, proposals_dir)
        return GenerationReport(
            proposals=proposals,
            written_paths=written_paths,
            proposals_dir=proposals_dir,
        )


def _require_unique_ids(proposals: Sequence[TestProposal]) -> None:
    counts = Counter(proposal.proposal_id for proposal in proposals)
    duplicated = sorted(proposal_id for proposal_id, count in counts.items() if count > 1)
    if duplicated:
        raise ValueError(f"duplicate proposal_id in batch: {', '.join(duplicated)}")
