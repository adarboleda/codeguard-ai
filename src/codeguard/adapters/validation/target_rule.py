"""Rule 3 of the validation chain: the proposal must call the target function (CG-10).

Black-box design: the expected signature is built from the contract declaration
(``FunctionContract.signature``), which ``YamlSpecRepository`` already verified against
``inspect.signature`` of the real function. ``sciref`` is never imported here.
"""

import ast
import inspect
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from codeguard.adapters.validation.ast_names import NameResolver
from codeguard.domain import FunctionContract, RejectionReason, TestProposal, ValidationVerdict

_ANY_VALUE = object()  # placeholder argument/default: bind() only checks names and arity
_P = inspect.Parameter


@dataclass(frozen=True)
class _TargetCall:
    """A call to the target found in the proposal, with the arguments it receives."""

    lineno: int
    args: tuple[ast.expr, ...]
    keywords: tuple[ast.keyword, ...]


class TargetRule:
    """Rejects proposals that never call the target or call it with invalid arguments."""

    name = "target"

    def __init__(self, contracts: Iterable[FunctionContract]) -> None:
        self._signatures = {
            contract.qualified_name: signature_from_declaration(contract.signature)
            for contract in contracts
        }
        if not self._signatures:
            raise ValueError("TargetRule needs at least one FunctionContract")

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """Return ``None`` if every call to the target binds to its signature."""
        target = proposal.target_qualified_name
        signature = self._signatures.get(target)
        if signature is None:
            detail = f"no contract for {target}"
            return self._reject(proposal, RejectionReason.TARGET_NOT_CALLED, detail)
        calls = list(find_target_calls(ast.parse(proposal.code), target))
        if not calls:
            detail = f"no call to {target}; import it from {proposal.target_module} and call it"
            return self._reject(proposal, RejectionReason.TARGET_NOT_CALLED, detail)
        for call in calls:
            error = _bind_error(signature, call)
            if error is not None:
                detail = f"line {call.lineno}: {error}"
                return self._reject(proposal, RejectionReason.INVALID_SIGNATURE, detail)
        return None

    def _reject(
        self, proposal: TestProposal, reason: RejectionReason, detail: str
    ) -> ValidationVerdict:
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=reason,
            detail=detail,
            rule_name=self.name,
        )


def signature_from_declaration(declaration: str) -> inspect.Signature:
    """Build a Signature from ``"name(a, b, c=1)"``; defaults are placeholders."""
    try:
        node = ast.parse(f"def {declaration}: pass").body[0]
    except SyntaxError as error:
        raise ValueError(f"invalid signature declaration {declaration!r}: {error.msg}") from error
    if not isinstance(node, ast.FunctionDef):
        raise ValueError(f"invalid signature declaration {declaration!r}")
    return inspect.Signature(_parameters(node.args))


def _parameters(args: ast.arguments) -> list[inspect.Parameter]:
    positional = [*args.posonlyargs, *args.args]
    first_default = len(positional) - len(args.defaults)
    params = [
        _P(
            arg.arg,
            _P.POSITIONAL_ONLY if index < len(args.posonlyargs) else _P.POSITIONAL_OR_KEYWORD,
            default=_ANY_VALUE if index >= first_default else _P.empty,
        )
        for index, arg in enumerate(positional)
    ]
    if args.vararg:
        params.append(_P(args.vararg.arg, _P.VAR_POSITIONAL))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        has_default = default is not None
        params.append(_P(arg.arg, _P.KEYWORD_ONLY, default=_ANY_VALUE if has_default else _P.empty))
    if args.kwarg:
        params.append(_P(args.kwarg.arg, _P.VAR_KEYWORD))
    return params


def find_target_calls(tree: ast.Module, target: str) -> Iterator[_TargetCall]:
    """Yield every call to ``target`` (``module.function``) in the proposal.

    Also recognises the callable form ``pytest.raises(Error, target, *args)``.
    """
    resolver = NameResolver(tree, target)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            arguments = resolver.target_call_arguments(node)
            if arguments is not None:
                yield _TargetCall(node.lineno, *arguments)


def _bind_error(signature: inspect.Signature, call: _TargetCall) -> str | None:
    """Return the TypeError message if the call cannot bind, else ``None``.

    Calls with ``*args`` or ``**kwargs`` cannot be checked statically and are accepted.
    """
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return None
    if any(keyword.arg is None for keyword in call.keywords):
        return None
    positional = [_ANY_VALUE] * len(call.args)
    named = {str(keyword.arg): _ANY_VALUE for keyword in call.keywords}
    try:
        signature.bind(*positional, **named)
    except TypeError as error:
        return str(error)
    return None
