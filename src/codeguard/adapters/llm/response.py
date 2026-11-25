"""Turn a model's answer into test modules: one module per test function (CG-31).

Splitting keeps one wrong expectation from discarding every other test of the same
answer, and makes the validity rate comparable with the template proposals.
"""

import ast
import re

_CODE_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """The first fenced code block, or the whole answer if there is none."""
    match = _CODE_BLOCK.search(text)
    code = match.group(1) if match else text
    return code.strip() + "\n"


def split_tests(code: str, max_tests: int) -> list[str]:
    """One module per ``test_*`` function, each with the module's shared statements.

    If the code does not parse or has no test functions it is returned unchanged as a
    single module, so the validator rejects it with its real reason (syntax / no assert).
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return [code]
    tests = [node for node in tree.body if _is_test(node)]
    if not tests:
        return [code]
    shared = [node for node in tree.body if not _is_test(node) and not _is_other_def(node)]
    modules = [ast.Module(body=[*shared, test], type_ignores=[]) for test in tests[:max_tests]]
    return [ast.unparse(module) + "\n" for module in modules]


def _is_test(node: ast.stmt) -> bool:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def _is_other_def(node: ast.stmt) -> bool:
    """Test classes are dropped: the prompt asks for plain test functions."""
    return isinstance(node, ast.ClassDef)
