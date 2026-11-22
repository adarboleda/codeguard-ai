"""Jinja2 template-based ProposalSource adapter (CG-07)."""

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader, StrictUndefined, select_autoescape

from codeguard.domain import (
    CaseKind,
    ContractCase,
    FunctionContract,
    ProposalSourceKind,
    TestProposal,
)

DEFAULT_REL_TOL = 1e-9

_TEMPLATE_NORMAL = "test_normal.py.j2"
_TEMPLATE_BOUNDARY = "test_boundary.py.j2"
_TEMPLATE_FLOAT = "test_float.py.j2"
_TEMPLATE_EXCEPTION = "test_exception.py.j2"


class TemplateProposalSource:
    """Deterministic ``ProposalSource`` backed by Jinja2 templates per case class."""

    def __init__(
        self,
        *,
        rel_tol: float = DEFAULT_REL_TOL,
        templates_dir: Path | None = None,
    ) -> None:
        if math.isnan(rel_tol) or rel_tol < 0:
            raise ValueError("rel_tol must be non-negative")
        self._rel_tol = rel_tol
        loader = (
            FileSystemLoader(templates_dir)
            if templates_dir is not None
            else PackageLoader("codeguard", "templates")
        )
        self._env = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "xml"]),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        """Generate one ``TestProposal`` per ``ContractCase`` across all contracts."""
        return tuple(
            self._render_case(contract, case) for contract in contracts for case in contract.cases
        )

    def _render_case(self, contract: FunctionContract, case: ContractCase) -> TestProposal:
        case_slug = _slugify(case.case_id)
        template_name = _select_template(case)
        template = self._env.get_template(template_name)
        rel_tol = self._rel_tol if case.rel_tol is None else case.rel_tol
        rendered = template.render(
            target_module=contract.module,
            target_function=contract.name,
            case_id=case.case_id,
            case_slug=case_slug,
            case_kind=case.kind.value,
            description=_sanitize_docstring_text(case.description),
            call_args_str=_format_call_args(case.inputs),
            expected_literal=_format_python_literal(case.expected),
            expected_is_bool=isinstance(case.expected, bool),
            expected_exception=case.expected_exception or "",
            rel_tol=_format_rel_tol(rel_tol),
        )
        code = rendered.rstrip("\n") + "\n"
        return TestProposal(
            proposal_id=f"tpl-{contract.name}-{case_slug}",
            target_module=contract.module,
            target_function=contract.name,
            source=ProposalSourceKind.TEMPLATE,
            code=code,
            case_ids=(case.case_id,),
            file_name=f"test_{contract.name}_{case_slug}.py",
        )


def _select_template(case: ContractCase) -> str:
    """Choose the Jinja2 template corresponding to the contract case class."""
    if case.expects_exception:
        return _TEMPLATE_EXCEPTION
    if _contains_float(case.expected):
        return _TEMPLATE_FLOAT
    if case.kind is CaseKind.BOUNDARY:
        return _TEMPLATE_BOUNDARY
    return _TEMPLATE_NORMAL


def _contains_float(value: object) -> bool:
    """Return True if ``value`` is a float (excluding bool) or contains a float."""
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return True
    if isinstance(value, list | tuple):
        return any(_contains_float(item) for item in value)
    return False


def _format_call_args(inputs: Mapping[str, object]) -> str:
    """Render keyword argument pairs ``param=literal`` for a function call."""
    return ", ".join(f"{name}={_format_python_literal(value)}" for name, value in inputs.items())


def _format_float_literal(value: float) -> str:
    """Render a float literal, handling NaN and +/-inf without bare names."""
    if math.isnan(value):
        return 'float("nan")'
    if math.isinf(value):
        return 'float("inf")' if value > 0 else 'float("-inf")'
    return repr(value)


def _format_tuple_literal(value: tuple[object, ...]) -> str:
    """Render a tuple literal, preserving the trailing comma for 1-tuples."""
    items = ", ".join(_format_python_literal(item) for item in value)
    return f"({items},)" if len(value) == 1 else f"({items})"


def _format_dict_literal(value: dict[object, object]) -> str:
    """Render a dict literal with recursively formatted keys and values."""
    pairs = ", ".join(
        f"{_format_python_literal(key)}: {_format_python_literal(val)}"
        for key, val in value.items()
    )
    return f"{{{pairs}}}"


def _format_python_literal(value: object) -> str:
    """Render a Python source literal, handling bool, NaN, and +/-inf safely."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return _format_float_literal(value)
    if isinstance(value, list):
        items = ", ".join(_format_python_literal(item) for item in value)
        return f"[{items}]"
    if isinstance(value, tuple):
        return _format_tuple_literal(value)
    if isinstance(value, dict):
        return _format_dict_literal(value)
    return repr(value)


def _format_rel_tol(rel_tol: float) -> str:
    """Format a float relative tolerance cleanly (e.g. ``1e-9``)."""
    return repr(rel_tol).replace("e-0", "e-", 1)


def _sanitize_docstring_text(text: str) -> str:
    """Keep docstring metadata single-line and free of closing triple quotes."""
    collapsed = " ".join(text.splitlines()).strip()
    return collapsed.replace('"""', "'''")


def _slugify(text: str) -> str:
    """Convert a case ID into a lowercase Python-safe identifier suffix."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    if not slug:
        raise ValueError(f"cannot build valid identifier slug from {text!r}")
    return slug
