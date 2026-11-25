"""Black-box prompt for one function: signature, docstring and contract only (CG-31).

The implementation is never sent: the docstring is read with ``ast`` and the
function body is discarded. The contract cases' expected values are not sent either,
so the model must work out the expectations itself; wrong ones are caught by the
validator (``WRONG_EXPECTATION``), because the LLM is not the oracle.
"""

import ast
from pathlib import Path

from codeguard.domain import FunctionContract
from codeguard.domain.llm import LlmPrompt

SYSTEM_PROMPT = (
    "You write pytest tests for a Python function whose source code you cannot see. "
    "Use only the public description you are given. Reply with exactly one Python module "
    "inside a single ```python code block, and nothing else."
)

_RULES = """\
Write between {min_tests} and {max_tests} independent test functions named test_<what_it_checks>.
Cover normal inputs, boundary inputs and invalid inputs.
Rules:
- every test calls {name} and asserts on its result, or uses pytest.raises for invalid inputs;
- compare floats with pytest.approx(expected, rel=1e-9);
- import only pytest, math and the target, exactly as: from {module} import {name}
- no fixtures, no randomness, no file or network access, no helper classes;
- each test is self-contained and does not depend on the others."""


def read_docstring(reference_dir: Path, contract: FunctionContract) -> str:
    """Docstring of the target function, read with ``ast`` (the body is never used)."""
    path = reference_dir.joinpath(*contract.module.split(".")).with_suffix(".py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == contract.name:
            return ast.get_docstring(node) or ""
    return ""


def build_prompt(
    contract: FunctionContract, docstring: str, *, min_tests: int = 4, max_tests: int = 8
) -> LlmPrompt:
    """Describe the function as a black box: name, import, signature, docstring, contract."""
    parts = [
        f"Target function: {contract.qualified_name}",
        f"Signature: {contract.signature}",
        f"Contract: {contract.docstring}",
    ]
    if docstring:
        parts.append(f'Docstring:\n"""\n{docstring}\n"""')
    rules = _RULES.format(
        min_tests=min_tests, max_tests=max_tests, name=contract.name, module=contract.module
    )
    return LlmPrompt(system=SYSTEM_PROMPT, user="\n\n".join([*parts, rules]))
