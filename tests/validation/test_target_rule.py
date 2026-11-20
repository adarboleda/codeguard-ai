"""Tests for TargetRule (CG-10): the proposal must call the target with valid arguments."""

from pathlib import Path

import pytest
from conftest import REFERENCE_DIR, ProposalFactory

from codeguard.adapters.specs import YamlSpecRepository
from codeguard.adapters.validation import TargetRule
from codeguard.adapters.validation.target_rule import signature_from_declaration
from codeguard.domain import FunctionContract, RejectionReason

CONTRACTS_FILE = Path(__file__).resolve().parents[2] / "specs" / "contracts.yaml"

WEIGHTED_MEAN = FunctionContract(
    module="sciref.numeric",
    name="weighted_mean",
    signature="weighted_mean(values, weights)",
    docstring="Σ(w·v) / Σw",
)
VALIDATE_RANGE = FunctionContract(
    module="sciref.validation",
    name="validate_range",
    signature="validate_range(value, lo, hi, inclusive=True)",
    docstring="lo <= value <= hi",
)


@pytest.fixture
def rule() -> TargetRule:
    return TargetRule([WEIGHTED_MEAN, VALIDATE_RANGE])


def _test_body(imports: str, call: str) -> str:
    return f"{imports}\n\n\ndef test_case() -> None:\n    assert {call} == 2.5\n"


@pytest.mark.parametrize(
    ("imports", "call"),
    [
        ("from sciref.numeric import weighted_mean", "weighted_mean([1, 3], [1, 3])"),
        ("from sciref.numeric import weighted_mean as wm", "wm([1, 3], [1, 3])"),
        ("from sciref import weighted_mean", "weighted_mean([1, 3], [1, 3])"),
        ("import sciref.numeric as num", "num.weighted_mean([1, 3], [1, 3])"),
        ("import sciref.numeric", "sciref.numeric.weighted_mean([1, 3], [1, 3])"),
        ("from sciref import numeric", "numeric.weighted_mean(values=[1, 3], weights=[1, 3])"),
    ],
)
def test_supported_import_styles_pass(
    rule: TargetRule, make_proposal: ProposalFactory, imports: str, call: str
) -> None:
    assert rule.check(make_proposal(code=_test_body(imports, call))) is None


def test_call_inside_pytest_raises_block_counts(
    rule: TargetRule, make_proposal: ProposalFactory
) -> None:
    code = (
        "import pytest\nfrom sciref.numeric import weighted_mean\n\n\n"
        "def test_empty() -> None:\n"
        "    with pytest.raises(ValueError):\n"
        "        weighted_mean([], [])\n"
    )
    assert rule.check(make_proposal(code=code)) is None


def test_pytest_raises_callable_form_counts(
    rule: TargetRule, make_proposal: ProposalFactory
) -> None:
    code = (
        "import pytest\nfrom sciref.numeric import weighted_mean\n\n\n"
        "def test_empty() -> None:\n"
        "    pytest.raises(ValueError, weighted_mean, [], [])\n"
    )
    assert rule.check(make_proposal(code=code)) is None


def test_calling_another_function_is_rejected(
    rule: TargetRule, make_proposal: ProposalFactory
) -> None:
    code = _test_body("from sciref.numeric import clamp", "clamp(5, 0, 10)")

    verdict = rule.check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.valid is False
    assert verdict.reason is RejectionReason.TARGET_NOT_CALLED
    assert verdict.rule_name == "target"
    assert "sciref.numeric.weighted_mean" in verdict.detail


def test_import_without_call_is_rejected(rule: TargetRule, make_proposal: ProposalFactory) -> None:
    code = _test_body("from sciref.numeric import weighted_mean", "1 + 1.5")

    verdict = rule.check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.reason is RejectionReason.TARGET_NOT_CALLED


def test_local_stub_with_same_name_is_rejected(
    rule: TargetRule, make_proposal: ProposalFactory
) -> None:
    code = (
        "from sciref.numeric import weighted_mean\n\n\n"
        "def weighted_mean(values, weights):\n    return 2.5\n\n\n"
        "def test_x() -> None:\n    assert weighted_mean([1, 3], [1, 3]) == 2.5\n"
    )

    verdict = rule.check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.reason is RejectionReason.TARGET_NOT_CALLED


@pytest.mark.parametrize(
    ("call", "message"),
    [
        ("weighted_mean([1, 3])", "missing a required argument: 'weights'"),
        ("weighted_mean([1], [1], [1])", "too many positional arguments"),
        ("weighted_mean([1], [1], wts=[1])", "got an unexpected keyword argument 'wts'"),
    ],
)
def test_invalid_arguments_are_rejected(
    rule: TargetRule, make_proposal: ProposalFactory, call: str, message: str
) -> None:
    code = _test_body("from sciref.numeric import weighted_mean", call)

    verdict = rule.check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.reason is RejectionReason.INVALID_SIGNATURE
    assert verdict.detail == f"line 5: {message}"


def test_one_bad_call_among_good_ones_is_rejected(
    rule: TargetRule, make_proposal: ProposalFactory
) -> None:
    code = (
        "from sciref.numeric import weighted_mean\n\n\n"
        "def test_x() -> None:\n"
        "    assert weighted_mean([1, 3], [1, 3]) == 2.5\n"
        "    assert weighted_mean([1, 3]) == 2.5\n"
    )

    verdict = rule.check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.detail.startswith("line 6:")


@pytest.mark.parametrize(
    ("call", "valid"),
    [
        ("validate_range(5, 0, 10)", True),
        ("validate_range(5, 0, 10, inclusive=False)", True),
        ("validate_range(5, 0, 10, False)", True),
        ("validate_range(5, 0, 10, True, 1)", False),
        ("validate_range(value=5, lo=0)", False),
    ],
)
def test_default_parameters(
    rule: TargetRule, make_proposal: ProposalFactory, call: str, valid: bool
) -> None:
    proposal = make_proposal(
        code=_test_body("from sciref.validation import validate_range", call),
        target_module="sciref.validation",
        target_function="validate_range",
    )

    assert (rule.check(proposal) is None) is valid


def test_star_arguments_are_not_checked(rule: TargetRule, make_proposal: ProposalFactory) -> None:
    code = _test_body("from sciref.numeric import weighted_mean", "weighted_mean(*([1], [1]))")

    assert rule.check(make_proposal(code=code)) is None


def test_target_without_contract_is_rejected(make_proposal: ProposalFactory) -> None:
    verdict = TargetRule([VALIDATE_RANGE]).check(make_proposal())

    assert verdict is not None
    assert verdict.reason is RejectionReason.TARGET_NOT_CALLED
    assert verdict.detail == "no contract for sciref.numeric.weighted_mean"


def test_rule_needs_contracts() -> None:
    with pytest.raises(ValueError, match="at least one"):
        TargetRule([])


def test_signature_from_declaration_keeps_kinds_and_defaults() -> None:
    signature = signature_from_declaration("f(a, /, b, c=1, *args, d, e=2, **kwargs)")

    kinds = [param.kind.name for param in signature.parameters.values()]
    assert list(signature.parameters) == ["a", "b", "c", "args", "d", "e", "kwargs"]
    assert kinds == [
        "POSITIONAL_ONLY",
        "POSITIONAL_OR_KEYWORD",
        "POSITIONAL_OR_KEYWORD",
        "VAR_POSITIONAL",
        "KEYWORD_ONLY",
        "KEYWORD_ONLY",
        "VAR_KEYWORD",
    ]


def test_invalid_declaration_raises() -> None:
    with pytest.raises(ValueError, match="invalid signature declaration"):
        signature_from_declaration("not a signature")


def test_every_case_of_the_real_contracts_binds(make_proposal: ProposalFactory) -> None:
    """Integration with CG-06: each contract case, written as a call, passes the rule."""
    contracts = YamlSpecRepository(CONTRACTS_FILE, search_paths=[REFERENCE_DIR]).load()
    rule = TargetRule(contracts)

    for contract in contracts:
        for case in contract.cases:
            args = ", ".join(f"{name}={value!r}" for name, value in case.inputs.items())
            code = (
                f"from {contract.module} import {contract.name}\n\n\n"
                f"def test_{case.case_id.replace('-', '_').lower()}() -> None:\n"
                f"    {contract.name}({args})\n"
            )
            proposal = make_proposal(
                code=code,
                proposal_id=case.case_id,
                target_module=contract.module,
                target_function=contract.name,
            )
            assert rule.check(proposal) is None, case.case_id
