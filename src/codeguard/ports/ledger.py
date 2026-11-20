"""Port for persisting the proposal ledger of a run."""

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from codeguard.domain.ledger import LedgerEntry


class LedgerRepository(Protocol):
    """Stores and reads back the ledger of one run (``out/<run_id>/``)."""

    def write(self, entries: Iterable[LedgerEntry], run_dir: Path) -> Path:
        """Write all entries for the run and return the ledger file path."""
        ...

    def read(self, path: Path) -> tuple[LedgerEntry, ...]:
        """Read a ledger file back into entries, in the original order."""
        ...
