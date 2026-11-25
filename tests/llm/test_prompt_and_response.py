"""Tests for the black-box prompt and the parsing of the model's answer (CG-31)."""

import ast
from pathlib import Path

import pytest

from codeguard.adapters.llm import build_prompt, extract_code, read_docstring, split_tests
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.domain import FunctionContract

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "reference"
CONTRACTS = YamlSpecRepository(REPO_ROOT / "specs" / "contracts.yaml", [REFERENCE_DIR]).load()
WEIGHTED_MEAN = next(c for c in CONTRACTS if c.name == "weighted_mean")


def _implementation_lines(contract_module: str, name: str) -> list[str]:
    """Statements of the real function body (what must never reach the model)."""
    path = REFERENCE_DIR.joinpath(*contract_module.split(".")).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    body = function.body[1:] if ast.get_docstring(function) else function.body
    return [ast.unparse(statement) for statement in body]


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.name)
def test_prompt_is_black_box(contract: FunctionContract) -> None:
    prompt = build_prompt(contract, read_docstring(REFERENCE_DIR, contract))

    assert contract.signature in prompt.user
    assert f"from {contract.module} import {contract.name}" in prompt.user
    for statement in _implementation_lines(contract.module, contract.name):
        assert statement not in prompt.user, "implementation code leaked into the prompt"
    for case in contract.cases:
        assert case.description not in prompt.user, "oracle derivation leaked into the prompt"


def test_prompt_contains_contract_docstring_and_rules() -> None:
    docstring = read_docstring(REFERENCE_DIR, WEIGHTED_MEAN)

    prompt = build_prompt(WEIGHTED_MEAN, docstring, max_tests=5)

    assert docstring and docstring in prompt.user
    assert "Contract: Σ(w·v) / Σw" in prompt.user
    assert "between 4 and 5 independent test functions" in prompt.user
    assert "pytest.approx(expected, rel=1e-9)" in prompt.user
    assert "```python" in prompt.system


def test_docstring_of_unknown_function_or_module_is_empty(tmp_path: Path) -> None:
    other = WEIGHTED_MEAN.__class__(
        module="sciref.numeric", name="nope", signature="nope()", docstring="x"
    )
    assert read_docstring(REFERENCE_DIR, other) == ""
    assert read_docstring(tmp_path, WEIGHTED_MEAN) == ""


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Here:\n```python\nimport pytest\n```\nbye", "import pytest\n"),
        ("```py\nx = 1\n```", "x = 1\n"),
        ("```\ny = 2\n```", "y = 2\n"),
        ("z = 3", "z = 3\n"),
    ],
)
def test_extract_code(text: str, code: str) -> None:
    assert extract_code(text) == code


ANSWER = """\
import pytest
from sciref.numeric import weighted_mean

TOL = 1e-9


def test_basic():
    assert weighted_mean([1, 3], [1, 3]) == pytest.approx(2.5, rel=TOL)


class TestIgnored:
    def test_method(self):
        assert weighted_mean([1], [1]) == 1


def test_empty():
    with pytest.raises(ValueError):
        weighted_mean([], [])


def test_third():
    assert weighted_mean([2], [1]) == 2
"""


def test_split_gives_one_module_per_test_with_shared_imports() -> None:
    modules = split_tests(ANSWER, max_tests=8)

    assert len(modules) == 3
    for module in modules:
        tree = ast.parse(module)
        tests = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        assert len(tests) == 1
        assert "from sciref.numeric import weighted_mean" in module
        assert "TOL = 1e-09" in module
        assert "TestIgnored" not in module


def test_split_respects_the_maximum() -> None:
    assert len(split_tests(ANSWER, max_tests=2)) == 2


@pytest.mark.parametrize("code", ["def test_x(:\n", "x = 1\n", "\0"])
def test_unparsable_or_testless_code_is_kept_as_one_module(code: str) -> None:
    assert split_tests(code, max_tests=8) == [code]
