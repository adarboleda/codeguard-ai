"""Rule 4 of the validation chain: every test must verify the target's result (CG-11).

A test is useful only if at least one ``assert`` or ``pytest.raises`` depends on a call
to the target function. Tautological assertions (``assert True``, ``assert x == x``,
comparisons between constants, ``... or True``) are rejected even next to good ones.
"""

import ast
from collections.abc import Iterator
from typing import TypeGuard

from codeguard.adapters.validation.ast_names import NameResolver
from codeguard.domain import RejectionReason, TestProposal, ValidationVerdict

_MAX_SNIPPET_CHARS = 80
_REFLEXIVE_OPERATORS = (ast.Eq, ast.Is, ast.LtE, ast.GtE)  # x OP x is always true

_Problem = tuple[RejectionReason, str]


class AssertionRule:
    """Rejects tests without useful assertions (``NO_ASSERTION`` / ``TAUTOLOGICAL_ASSERTION``)."""

    name = "assertions"

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """Return ``None`` if every test function checks the target's behaviour."""
        tree = ast.parse(proposal.code)
        resolver = NameResolver(tree, proposal.target_qualified_name)
        tests = list(_test_functions(tree))
        if not tests:
            return self._reject(proposal, (RejectionReason.NO_ASSERTION, "no test functions found"))
        for function in tests:
            problem = _inspect_test(function, resolver, proposal.target_qualified_name)
            if problem is not None:
                return self._reject(proposal, problem)
        return None

    def _reject(self, proposal: TestProposal, problem: _Problem) -> ValidationVerdict:
        reason, detail = problem
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=reason,
            detail=detail,
            rule_name=self.name,
        )


def _test_functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Functions pytest would collect: ``test*`` at module level or in ``Test*`` classes."""
    for node in tree.body:
        if _is_test_function(node):
            yield node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            yield from (item for item in node.body if _is_test_function(item))


def _is_test_function(node: ast.stmt) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def _inspect_test(
    function: ast.FunctionDef | ast.AsyncFunctionDef, resolver: NameResolver, target: str
) -> _Problem | None:
    asserts = [node for node in ast.walk(function) if isinstance(node, ast.Assert)]
    for statement in asserts:
        why = _tautology(statement.test, resolver)
        if why is not None:
            snippet = _snippet(statement.test)
            detail = f"{function.name}, line {statement.lineno}: `assert {snippet}` {why}"
            return RejectionReason.TAUTOLOGICAL_ASSERTION, detail
    raises = list(_raises_checks(function, resolver))
    if not asserts and not raises:
        return RejectionReason.NO_ASSERTION, f"{function.name} has no assert or pytest.raises"
    tainted = _names_derived_from_target(function, resolver)
    checks_target = any(raises) or any(
        _depends_on_target(statement.test, resolver, tainted) for statement in asserts
    )
    if not checks_target:
        detail = f"{function.name}: no assert or pytest.raises checks the result of {target}"
        return RejectionReason.NO_ASSERTION, detail
    return None


def _tautology(expr: ast.expr, resolver: NameResolver) -> str | None:
    """Explain why an assertion is always true or constant, or return ``None``."""
    if _is_constant(expr, resolver):
        return "does not depend on the code under test"
    if isinstance(expr, ast.Compare) and _compares_with_itself(expr):
        return "compares a value with itself"
    if _is_or_with_true_constant(expr):
        return "is always true (`or` with a true constant)"
    return None


def _is_or_with_true_constant(expr: ast.expr) -> bool:
    return (
        isinstance(expr, ast.BoolOp)
        and isinstance(expr.op, ast.Or)
        and any(isinstance(value, ast.Constant) and bool(value.value) for value in expr.values)
    )


def _is_constant(expr: ast.expr, resolver: NameResolver) -> bool:
    """No runtime value involved: only literals, optionally wrapped in ``pytest.approx``."""
    for node in ast.walk(expr):
        if isinstance(node, ast.Name):
            qualified = resolver.qualified(node)
            if qualified is None or not qualified.startswith("pytest"):
                return False
    return True


def _compares_with_itself(compare: ast.Compare) -> bool:
    operands = [compare.left, *compare.comparators]
    return any(
        isinstance(operator, _REFLEXIVE_OPERATORS) and ast.dump(left) == ast.dump(right)
        for operator, left, right in zip(compare.ops, operands, operands[1:], strict=False)
    )


def _raises_checks(
    function: ast.FunctionDef | ast.AsyncFunctionDef, resolver: NameResolver
) -> Iterator[bool]:
    """Yield one bool per ``pytest.raises`` use: does it wrap a call to the target?"""
    for node in ast.walk(function):
        if isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and resolver.is_pytest_raises(expr):
                    yield any(resolver.contains_target_call(statement) for statement in node.body)
        elif isinstance(node, ast.Call) and resolver.is_pytest_raises(node) and len(node.args) >= 2:
            yield resolver.is_target(node.args[1])  # callable form: pytest.raises(E, f, ...)


def _names_derived_from_target(
    function: ast.FunctionDef | ast.AsyncFunctionDef, resolver: NameResolver
) -> set[str]:
    """Variables observed through the target (fixpoint).

    A variable counts if it holds a value computed from a call to the target, or if it
    was passed to the target: asserting on it afterwards checks a side effect, e.g. that
    ``normalize_minmax(original)`` does not mutate ``original`` (part of the contract).
    """
    tainted = _names_passed_to_target(function, resolver)
    assignments = [
        (targets, value)
        for node in ast.walk(function)
        for targets, value in _assignment(node)
        if value is not None
    ]
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            if _depends_on_target(value, resolver, tainted):
                new_names = _stored_names(targets) - tainted
                if new_names:
                    tainted |= new_names
                    changed = True
    return tainted


def _names_passed_to_target(
    function: ast.FunctionDef | ast.AsyncFunctionDef, resolver: NameResolver
) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        arguments = resolver.target_call_arguments(node)
        if arguments is None:
            continue
        args, keywords = arguments
        for expr in [*args, *(keyword.value for keyword in keywords)]:
            names.update(child.id for child in ast.walk(expr) if isinstance(child, ast.Name))
    return names


def _assignment(node: ast.AST) -> Iterator[tuple[list[ast.expr], ast.expr | None]]:
    if isinstance(node, ast.Assign):
        yield node.targets, node.value
    elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr):
        yield [node.target], node.value


def _stored_names(targets: list[ast.expr]) -> set[str]:
    return {
        node.id
        for target in targets
        for node in ast.walk(target)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _depends_on_target(expr: ast.AST, resolver: NameResolver, tainted: set[str]) -> bool:
    """True if ``expr`` calls the target or reads a variable derived from it."""
    if resolver.contains_target_call(expr):
        return True
    return any(
        isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in tainted
        for node in ast.walk(expr)
    )


def _snippet(expr: ast.expr) -> str:
    text = ast.unparse(expr)
    return text if len(text) <= _MAX_SNIPPET_CHARS else f"{text[: _MAX_SNIPPET_CHARS - 3]}..."
