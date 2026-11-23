"""Run the registered static rules over Python files (CG-15)."""

import ast
from collections.abc import Iterable
from pathlib import Path

from codeguard.domain import Finding
from codeguard.ports.static import StaticRule

from .rules import registered_rules


class ScanError(Exception):
    """A file could not be analysed: it is not valid Python or not UTF-8 text."""

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(f"{file_path}: {reason}")
        self.file_path = file_path
        self.reason = reason


def scan_source(
    source: str, file_path: str, rules: Iterable[StaticRule] | None = None
) -> tuple[Finding, ...]:
    """Parse ``source`` and return the findings of ``rules`` (default: all registered).

    Raises ``ScanError`` if ``source`` is not valid Python.
    """
    try:
        module = ast.parse(source, filename=file_path)
    except SyntaxError as error:
        raise ScanError(file_path, f"sintaxis no válida en la línea {error.lineno}") from error
    lines = source.splitlines()
    active = tuple(registered_rules() if rules is None else rules)
    findings = [finding for rule in active for finding in rule.check(module, file_path, lines)]
    return tuple(sorted(findings, key=lambda f: (f.file_path, f.line, f.column, f.rule_id)))


def scan_paths(
    paths: Iterable[Path],
    rules: Iterable[StaticRule] | None = None,
    errors: list[ScanError] | None = None,
) -> tuple[Finding, ...]:
    """Scan each ``.py`` file in ``paths`` (directories are walked recursively).

    A file that cannot be analysed is appended to ``errors`` and the scan continues
    with the rest. If ``errors`` is None, the first such file raises ``ScanError``
    instead, so unanalysed code is never skipped silently.
    """
    rule_tuple = tuple(rules) if rules is not None else None
    findings: list[Finding] = []
    for root in paths:
        files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
                findings.extend(scan_source(text, path.as_posix(), rule_tuple))
            except UnicodeDecodeError as error:
                failure = ScanError(path.as_posix(), f"no es texto UTF-8 ({error.reason})")
                if errors is None:
                    raise failure from error
                errors.append(failure)
            except ScanError as failure:
                if errors is None:
                    raise
                errors.append(failure)
    return tuple(findings)
