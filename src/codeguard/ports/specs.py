"""Port for loading and validating function contract specifications."""

from typing import Protocol

from codeguard.domain import FunctionContract


class SpecRepository(Protocol):
    """Source of validated ``FunctionContract`` specifications."""

    def load(self) -> tuple[FunctionContract, ...]:
        """Load and validate all function contracts, raising ``SpecError`` on failure."""
        ...
