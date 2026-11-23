"""Run the registered static rules over Python files (CG-15)."""

import ast
from collections.abc import Iterable
from pathlib import Path

from codeguard.domain import Finding
from codeguard.ports.static import StaticRule

from .rules import registered_rules


def scan_source(
    source: str, file_path: str, rules: Iterable[StaticRule] | None = None
) -> tuple[Finding, ...]:
    """Parse ``source`` and return the findings of ``rules`` (default: all registered)."""
    module = ast.parse(source, filename=file_path)
    lines = source.splitlines()
    active = tuple(registered_rules() if rules is None else rules)
    findings = [finding for rule in active for finding in rule.check(module, file_path, lines)]
    return tuple(sorted(findings, key=lambda f: (f.file_path, f.line, f.column, f.rule_id)))


def scan_paths(
    paths: Iterable[Path], rules: Iterable[StaticRule] | None = None
) -> tuple[Finding, ...]:
    """Scan each ``.py`` file in ``paths`` (directories are walked recursively)."""
    rule_tuple = tuple(rules) if rules is not None else None
    findings: list[Finding] = []
    for root in paths:
        files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
        for path in files:
            text = path.read_text(encoding="utf-8")
            findings.extend(scan_source(text, path.as_posix(), rule_tuple))
    return tuple(findings)
