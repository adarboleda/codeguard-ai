"""Domain exception hierarchy for CodeGuard AI."""


class CodeGuardError(Exception):
    """Base exception for actionable domain and pipeline errors."""


class SpecError(CodeGuardError):
    """Raised when contract specifications or target signatures are invalid."""


class IntegrityError(CodeGuardError):
    """Raised when the reference package ``sciref`` fails SHA-256 integrity verification."""
