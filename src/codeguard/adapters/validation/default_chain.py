"""The validation chain used by ``codeguard validate`` and ``codeguard all`` (one source).

Order (plan, section 2.1): generation error -> syntax -> import -> target function ->
useful assertions -> expected values on the original code (LLM proposals only).
"""

from pathlib import Path

from codeguard.adapters.execution import DEFAULT_TIMEOUT_SECONDS, PytestSubprocessRunner
from codeguard.adapters.validation.assertion_rule import AssertionRule
from codeguard.adapters.validation.expectation_rule import ExpectationRule
from codeguard.adapters.validation.generation_error_rule import GenerationErrorRule
from codeguard.adapters.validation.import_rule import DEFAULT_TIMEOUT_SECONDS as IMPORT_TIMEOUT
from codeguard.adapters.validation.import_rule import ImportRule
from codeguard.adapters.validation.syntax_rule import SyntaxRule
from codeguard.adapters.validation.target_rule import TargetRule
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import FunctionContract


def default_validation_chain(
    contracts: tuple[FunctionContract, ...],
    reference_dir: Path,
    import_timeout_seconds: float = IMPORT_TIMEOUT,
    runner_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ValidationChain:
    """All rules, in plan order. Template proposals skip the (slow) expectation rule."""
    return ValidationChain(
        [
            GenerationErrorRule(),
            SyntaxRule(),
            ImportRule(search_paths=[reference_dir], timeout_seconds=import_timeout_seconds),
            TargetRule(contracts),
            AssertionRule(),
            ExpectationRule(PytestSubprocessRunner(runner_timeout_seconds), reference_dir),
        ]
    )
