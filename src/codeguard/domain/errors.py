"""Domain exception hierarchy for CodeGuard AI."""


class CodeGuardError(Exception):
    """Base exception for actionable domain and pipeline errors."""


class SpecError(CodeGuardError):
    """Raised when contract specifications or target signatures are invalid."""
