"""Ports for test proposal generation and persistence (CG-07, CG-08)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from codeguard.domain import FunctionContract, TestProposal


class ProposalSource(Protocol):
    """Strategy interface for generating test proposals from contracts."""

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        """Generate candidate test proposals for the given function contracts."""
        ...


class ProposalWriter(Protocol):
    """Port for writing generated test proposals to disk."""

    def write(self, proposals: Sequence[TestProposal], proposals_dir: Path) -> tuple[Path, ...]:
        """Persist each proposal as a ``test_*.py`` file in ``proposals_dir``."""
        ...


class ProposalReader(Protocol):
    """Port for reading persisted test proposals back from disk."""

    def read(self, proposals_dir: Path) -> tuple[TestProposal, ...]:
        """Load ``TestProposal`` objects from ``proposals_dir``."""
        ...
