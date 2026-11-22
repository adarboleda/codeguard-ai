"""Static security rules CG001 and CG002 (CG-15), registered by decorator.

Both rules work on the ``ast`` of a module. Only calls by simple names are
checked (``eval``, ``exec``, ``subprocess.*``, ``os.system``); aliases and
indirect calls are documented limits, not detections.
"""

import ast
from collections.abc import Callable

from codeguard.domain import Finding, Severity
from codeguard.ports.static import StaticRule

_REGISTRY: list[StaticRule] = []

_DYNAMIC_EXEC_NAMES = frozenset({"eval", "exec"})
_SUBPROCESS_FUNCTIONS = frozenset({"run", "call", "Popen", "check_call", "check_output"})


def register(rule_cls: Callable[[], StaticRule]) -> Callable[[], StaticRule]:
    """Class decorator that adds one instance of ``rule_cls`` to the registry."""
    _REGISTRY.append(rule_cls())
    return rule_cls


def registered_rules() -> tuple[StaticRule, ...]:
    """Every rule registered so far, in registration order."""
    return tuple(_REGISTRY)


def _snippet(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


@register
class DynamicExecutionRule:
    """CG001: ``eval`` or ``exec`` called with an argument that is not a string literal."""

    rule_id = "CG001"
    severity = Severity.HIGH

    def check(self, module: ast.Module, file_path: str, lines: list[str]) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            name = node.func.id
            if name not in _DYNAMIC_EXEC_NAMES or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str | bytes):
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    snippet=_snippet(lines, node.lineno),
                    message=f"{name}() recibe un argumento que no es un literal de texto",
                    recommendation=(
                        "No ejecutar código construido en tiempo de ejecución; para datos usar "
                        "ast.literal_eval y para acciones una tabla de funciones permitidas"
                    ),
                    severity=self.severity,
                )
            )
        return findings


@register
class ShellExecutionRule:
    """CG002: ``subprocess`` with ``shell=True`` or any ``os.system`` call."""

    rule_id = "CG002"
    severity = Severity.HIGH

    def check(self, module: ast.Module, file_path: str, lines: list[str]) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            if not isinstance(owner, ast.Name):
                continue
            message = _shell_message(owner.id, node.func.attr, node)
            if message is None:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    snippet=_snippet(lines, node.lineno),
                    message=message,
                    recommendation=(
                        "Pasar la orden como lista de argumentos sin shell=True, "
                        "por ejemplo subprocess.run([...], check=True)"
                    ),
                    severity=self.severity,
                )
            )
        return findings


def _shell_message(owner: str, attr: str, node: ast.Call) -> str | None:
    if owner == "os" and attr == "system":
        return "os.system() ejecuta una cadena en el shell"
    if owner == "subprocess" and attr in _SUBPROCESS_FUNCTIONS and _has_shell_true(node):
        return f"subprocess.{attr}() con shell=True"
    return None


def _has_shell_true(node: ast.Call) -> bool:
    return any(
        keyword.arg == "shell"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in node.keywords
    )
