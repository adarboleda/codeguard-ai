"""Tests for GenerationErrorRule and ExpectationRule (CG-31: the LLM is not the oracle)."""

import pytest
from conftest import REFERENCE_DIR, ProposalFactory

from codeguard.adapters.execution import PytestSubprocessRunner
from codeguard.adapters.validation import ExpectationRule, GenerationErrorRule
from codeguard.domain import ProposalSourceKind, RejectionReason
from codeguard.domain.llm import GENERATION_ERROR_MARKER

GROQ = ProposalSourceKind.GROQ
HEADER = "import pytest\nfrom sciref.numeric import weighted_mean\n\n\n"


@pytest.fixture
def rule() -> ExpectationRule:
    return ExpectationRule(PytestSubprocessRunner(timeout_seconds=30), REFERENCE_DIR)


def test_generation_error_placeholder_is_rejected(make_proposal: ProposalFactory) -> None:
    code = f"{GENERATION_ERROR_MARKER} sciref.numeric.clamp: APITimeoutError: timed out\n"

    verdict = GenerationErrorRule().check(make_proposal(code=code, source=GROQ))

    assert verdict is not None
    assert verdict.reason is RejectionReason.GENERATION_ERROR
    assert verdict.detail == "sciref.numeric.clamp: APITimeoutError: timed out"
    assert verdict.rule_name == "generation"


def test_normal_code_is_not_a_generation_error(make_proposal: ProposalFactory) -> None:
    assert GenerationErrorRule().check(make_proposal()) is None


def test_correct_expectation_passes(rule: ExpectationRule, make_proposal: ProposalFactory) -> None:
    code = (
        HEADER + "def test_ok():\n    assert weighted_mean([1, 3], [1, 3]) == pytest.approx(2.5)\n"
    )

    assert rule.check(make_proposal(code=code, source=GROQ)) is None


def test_wrong_expectation_is_rejected(
    rule: ExpectationRule, make_proposal: ProposalFactory
) -> None:
    code = HEADER + "def test_bad():\n    assert weighted_mean([1, 3], [1, 3]) == 2.0\n"

    verdict = rule.check(make_proposal(code=code, source=GROQ, file_name="test_groq_wm_01.py"))

    assert verdict is not None
    assert verdict.reason is RejectionReason.WRONG_EXPECTATION
    assert verdict.detail.startswith("tests/test_groq_wm_01.py::test_bad: assert 2.5 == 2.0")
    assert verdict.rule_name == "expectation"


def test_wrong_exception_expectation_is_rejected(
    rule: ExpectationRule, make_proposal: ProposalFactory
) -> None:
    code = (
        HEADER
        + "def test_bad():\n    with pytest.raises(TypeError):\n        weighted_mean([], [])\n"
    )

    verdict = rule.check(make_proposal(code=code, source=GROQ))

    assert verdict is not None
    assert verdict.reason is RejectionReason.WRONG_EXPECTATION


def test_setup_error_is_a_collection_error(
    rule: ExpectationRule, make_proposal: ProposalFactory
) -> None:
    code = HEADER + "def test_fixture(missing):\n    assert weighted_mean([1], [1]) == missing\n"

    verdict = rule.check(make_proposal(code=code, source=GROQ))

    assert verdict is not None
    assert verdict.reason is RejectionReason.COLLECTION_ERROR


def test_template_proposals_skip_the_rule(
    rule: ExpectationRule, make_proposal: ProposalFactory
) -> None:
    """Template expectations come from the hand-made oracle: this rule never runs them."""
    code = HEADER + "def test_bad():\n    assert weighted_mean([1, 3], [1, 3]) == 2.0\n"

    assert rule.check(make_proposal(code=code, source=ProposalSourceKind.TEMPLATE)) is None


def test_timeout_is_a_wrong_expectation(make_proposal: ProposalFactory) -> None:
    rule = ExpectationRule(PytestSubprocessRunner(timeout_seconds=2), REFERENCE_DIR)
    code = (
        HEADER
        + "import time\n\n\ndef test_slow():\n    time.sleep(30)\n"
        + "    assert weighted_mean([1], [1]) == 1\n"
    )

    verdict = rule.check(make_proposal(code=code, source=GROQ))

    assert verdict is not None
    assert verdict.reason is RejectionReason.WRONG_EXPECTATION
    assert verdict.detail == "timeout after 2 s"
