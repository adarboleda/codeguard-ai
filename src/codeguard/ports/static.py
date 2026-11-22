"""Port for static security rules run over Python source (CG-15)."""

import ast
from typing import Protocol

from codeguard.domain import Finding, Severity


class StaticRule(Protocol):
    """One static rule that inspects a parsed module and reports findings.

    Rules never raise for insecure code: reporting it is their job.
    """

    @property
    def rule_id(self) -> str:
        """Identifier such as ``CG001``, stored in ``Finding.rule_id``."""
        ...

    @property
    def severity(self) -> Severity:
        """Default severity of the findings this rule emits."""
        ...

    def check(self, module: ast.Module, file_path: str, lines: list[str]) -> list[Finding]:
        """Return every finding in ``module``; an empty list if the code is clean."""
        ...
