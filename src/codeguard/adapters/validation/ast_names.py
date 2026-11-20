"""Name resolution over a proposal's AST, shared by the validation rules.

Answers questions such as "is this expression the target function?" regardless of how
the proposal imported it (``from sciref.numeric import f``, ``import sciref.numeric as n``,
``from sciref import f``...).
"""

import ast

PYTEST_RAISES = "pytest.raises"


class NameResolver:
    """Resolves local names of one proposal to fully qualified names."""

    def __init__(self, tree: ast.Module, target: str) -> None:
        self._aliases = _import_aliases(tree)
        self._target_names = _accepted_names(target)

    def qualified(self, expr: ast.expr) -> str | None:
        """Resolve ``wm`` or ``num.weighted_mean`` to ``sciref.numeric.weighted_mean``."""
        parts: list[str] = []
        while isinstance(expr, ast.Attribute):
            parts.append(expr.attr)
            expr = expr.value
        if not isinstance(expr, ast.Name) or expr.id not in self._aliases:
            return None
        return ".".join([self._aliases[expr.id], *reversed(parts)])

    def is_target(self, expr: ast.expr) -> bool:
        """True if ``expr`` names the target function."""
        return self.qualified(expr) in self._target_names

    def is_pytest_raises(self, call: ast.Call) -> bool:
        """True for ``pytest.raises(...)`` however pytest was imported."""
        return self.qualified(call.func) == PYTEST_RAISES

    def target_call_arguments(
        self, call: ast.Call
    ) -> tuple[tuple[ast.expr, ...], tuple[ast.keyword, ...]] | None:
        """Arguments passed to the target by this call, or ``None`` if it is not a target call.

        Recognises ``target(...)`` and the callable form ``pytest.raises(Error, target, ...)``.
        """
        if self.is_target(call.func):
            return tuple(call.args), tuple(call.keywords)
        if self.is_pytest_raises(call) and len(call.args) >= 2 and self.is_target(call.args[1]):
            return tuple(call.args[2:]), tuple(call.keywords)
        return None

    def contains_target_call(self, node: ast.AST) -> bool:
        """True if any call inside ``node`` calls the target."""
        return any(
            isinstance(child, ast.Call) and self.target_call_arguments(child) is not None
            for child in ast.walk(node)
        )


def _accepted_names(target: str) -> set[str]:
    """``sciref.numeric.f`` is also reachable as ``sciref.f`` (package re-export).

    Accepting parent packages is safe: the import rule (earlier in the chain) has
    already proved that the proposal's imports resolve.
    """
    module, _, function = target.rpartition(".")
    parts = module.split(".")
    return {".".join([*parts[:size], function]) for size in range(1, len(parts) + 1)}


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map each imported local name to its fully qualified name."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    aliases[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if alias.name != "*":
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for name in _rebound_names(tree):
        aliases.pop(name, None)  # e.g. a local stub "def weighted_mean(...)" hides the import
    return aliases


def _rebound_names(tree: ast.Module) -> set[str]:
    """Names assigned or defined in the proposal (they shadow imported names)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names
