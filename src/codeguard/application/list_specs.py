"""Use case for loading and listing contract specifications (CG-06)."""

from codeguard.domain import FunctionContract
from codeguard.ports.specs import SpecRepository


class ListContracts:
    """Load validated function contracts via ``SpecRepository``."""

    def __init__(self, repository: SpecRepository) -> None:
        self._repository = repository

    def execute(self) -> tuple[FunctionContract, ...]:
        """Return all contracts provided by the repository."""
        return self._repository.load()
