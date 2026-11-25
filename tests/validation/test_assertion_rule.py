"""Tests for AssertionRule (CG-11): one test per accepted pattern and per rejected case."""

import pytest
from conftest import ProposalFactory

from codeguard.adapters.validation import AssertionRule
from codeguard.domain import ProposalSourceKind, RejectionReason, ValidationVerdict

HEADER = "import pytest\n\nfrom sciref.numeric import weighted_mean\n\n\n"

# Representative tautological seed for PA 03 (CG-08 will add the official one).
TAUTOLOGICAL_SEED = HEADER + (
    "def test_weighted_mean_seed() -> None:\n    weighted_mean([1, 3], [1, 3])\n    assert True\n"
)


def _test(body: str, name: str = "test_case") -> str:
    lines = "".join(f"    {line}\n" for line in body.splitlines())
    return f"{HEADER}def {name}() -> None:\n{lines}"


def _check(make_proposal: ProposalFactory, code: str) -> ValidationVerdict | None:
    return AssertionRule().check(make_proposal(code=code))


def _rejection(make_proposal: ProposalFactory, code: str) -> ValidationVerdict:
    verdict = _check(make_proposal, code)
    assert verdict is not None, "expected a rejection"
    assert verdict.valid is False
    assert verdict.rule_name == "assertions"
    return verdict


# ---------------------------------------------------------------- accepted


def test_assert_on_direct_call_passes(make_proposal: ProposalFactory) -> None:
    code = _test("assert weighted_mean([1, 3], [1, 3]) == pytest.approx(2.5, rel=1e-9)")
    assert _check(make_proposal, code) is None


def test_assert_on_result_variable_passes(make_proposal: ProposalFactory) -> None:
    code = _test(
        "result = weighted_mean([1, 3], [1, 3])\nexpected = 2.5\nassert result == expected"
    )
    assert _check(make_proposal, code) is None


def test_value_derived_from_result_passes(make_proposal: ProposalFactory) -> None:
    code = _test(
        "result = weighted_mean([1, 3], [1, 3])\nrounded = round(result, 2)\nassert rounded == 2.5"
    )
    assert _check(make_proposal, code) is None


def test_side_effect_on_an_argument_passes(make_proposal: ProposalFactory) -> None:
    """Regression (first real Groq run): checking that the input is not mutated is useful."""
    code = _test(
        "values = [1, 3]\ncopy = list(values)\n_ = weighted_mean(values, [1, 3])\n"
        "assert values == copy"
    )
    assert _check(make_proposal, code) is None


def test_side_effect_through_a_keyword_argument_passes(make_proposal: ProposalFactory) -> None:
    code = _test("w = [1, 3]\nweighted_mean([1, 3], weights=w)\nassert w == [1, 3]")
    assert _check(make_proposal, code) is None


def test_pytest_raises_block_with_target_passes(make_proposal: ProposalFactory) -> None:
    code = _test("with pytest.raises(ValueError):\n    weighted_mean([], [])")
    assert _check(make_proposal, code) is None


def test_pytest_raises_callable_form_passes(make_proposal: ProposalFactory) -> None:
    code = _test("pytest.raises(ValueError, weighted_mean, [], [])")
    assert _check(make_proposal, code) is None


def test_methods_of_test_classes_are_checked(make_proposal: ProposalFactory) -> None:
    code = HEADER + (
        "class TestWeightedMean:\n"
        "    def test_basic(self) -> None:\n"
        "        assert weighted_mean([1, 3], [1, 3]) == 2.5\n"
        "\n"
        "    def helper(self) -> None:\n"
        "        pass\n"
    )
    assert _check(make_proposal, code) is None


def test_helpers_outside_tests_are_ignored(make_proposal: ProposalFactory) -> None:
    code = HEADER + (
        "def build_inputs() -> list[int]:\n    return [1, 3]\n\n\n"
        "def test_basic() -> None:\n    assert weighted_mean(build_inputs(), [1, 3]) == 2.5\n"
    )
    assert _check(make_proposal, code) is None


# ---------------------------------------------------------------- NO_ASSERTION


def test_no_test_functions_is_rejected(make_proposal: ProposalFactory) -> None:
    verdict = _rejection(make_proposal, HEADER + "VALUE = weighted_mean([1], [1])\n")

    assert verdict.reason is RejectionReason.NO_ASSERTION
    assert verdict.detail == "no test functions found"


def test_only_calling_the_function_is_rejected(make_proposal: ProposalFactory) -> None:
    verdict = _rejection(make_proposal, _test("weighted_mean([1, 3], [1, 3])"))

    assert verdict.reason is RejectionReason.NO_ASSERTION
    assert verdict.detail == "test_case has no assert or pytest.raises"


def test_assertion_unrelated_to_the_target_is_rejected(make_proposal: ProposalFactory) -> None:
    code = _test("weighted_mean([1, 3], [1, 3])\nexpected = [2.5]\nassert len(expected) == 1")

    verdict = _rejection(make_proposal, code)

    assert verdict.reason is RejectionReason.NO_ASSERTION
    assert verdict.detail == (
        "test_case: no assert or pytest.raises checks the result of sciref.numeric.weighted_mean"
    )


def test_pytest_raises_without_target_is_rejected(make_proposal: ProposalFactory) -> None:
    code = _test("weighted_mean([1, 3], [1, 3])\nwith pytest.raises(ValueError):\n    int('x')")

    verdict = _rejection(make_proposal, code)

    assert verdict.reason is RejectionReason.NO_ASSERTION


# ---------------------------------------------------------------- TAUTOLOGICAL_ASSERTION


@pytest.mark.parametrize(
    ("assertion", "why"),
    [
        ("assert True", "does not depend on the code under test"),
        ("assert 1 == 1", "does not depend on the code under test"),
        ("assert 2.5 == pytest.approx(2.5)", "does not depend on the code under test"),
        ("assert result == result", "compares a value with itself"),
        ("assert result is result", "compares a value with itself"),
        ("assert result == 2.5 or True", "is always true (`or` with a true constant)"),
    ],
)
def test_tautological_assertions_are_rejected(
    make_proposal: ProposalFactory, assertion: str, why: str
) -> None:
    code = _test(f"result = weighted_mean([1, 3], [1, 3])\n{assertion}")

    verdict = _rejection(make_proposal, code)

    assert verdict.reason is RejectionReason.TAUTOLOGICAL_ASSERTION
    assert verdict.detail.startswith("test_case, line 8: `assert ")
    assert verdict.detail.endswith(why)


def test_tautology_next_to_a_good_assertion_is_rejected(make_proposal: ProposalFactory) -> None:
    code = _test("result = weighted_mean([1, 3], [1, 3])\nassert result == 2.5\nassert True")

    verdict = _rejection(make_proposal, code)

    assert verdict.reason is RejectionReason.TAUTOLOGICAL_ASSERTION


def test_one_bad_test_among_good_ones_is_rejected(make_proposal: ProposalFactory) -> None:
    code = HEADER + (
        "def test_good() -> None:\n    assert weighted_mean([1, 3], [1, 3]) == 2.5\n\n\n"
        "def test_bad() -> None:\n    weighted_mean([1, 3], [1, 3])\n"
    )

    verdict = _rejection(make_proposal, code)

    assert verdict.detail == "test_bad has no assert or pytest.raises"


def test_long_assertions_are_shortened_in_the_detail(make_proposal: ProposalFactory) -> None:
    code = _test("assert " + " + ".join(["1"] * 60) + " == 60")

    verdict = _rejection(make_proposal, code)

    assert "...`" in verdict.detail


def test_tautological_seed_is_rejected_with_its_reason(make_proposal: ProposalFactory) -> None:
    """PA 03: the tautological defective seed must be rejected and say why."""
    proposal = make_proposal(
        code=TAUTOLOGICAL_SEED,
        proposal_id="SEED-TAUTOLOGICAL",
        source=ProposalSourceKind.DEFECTIVE_SEED,
    )

    verdict = AssertionRule().check(proposal)

    assert verdict == ValidationVerdict(
        proposal_id="SEED-TAUTOLOGICAL",
        valid=False,
        reason=RejectionReason.TAUTOLOGICAL_ASSERTION,
        detail=(
            "test_weighted_mean_seed, line 8: `assert True` does not depend on the code under test"
        ),
        rule_name="assertions",
    )
