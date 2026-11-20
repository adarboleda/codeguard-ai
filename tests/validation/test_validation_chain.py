"""Tests for ValidationChain (CG-09): order, first rejection wins, nothing is dropped."""

import pytest
from conftest import REFERENCE_DIR, ProposalFactory

from codeguard.adapters.validation import ImportRule, SyntaxRule
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import RejectionReason, TestProposal, ValidationVerdict


class _FakeRule:
    """Test double: passes, or rejects with a fixed reason, and records calls."""

    def __init__(self, name: str, reject_with: RejectionReason | None = None) -> None:
        self.name = name
        self._reject_with = reject_with
        self.calls: list[str] = []

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        self.calls.append(proposal.proposal_id)
        if self._reject_with is None:
            return None
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=self._reject_with,
            detail=f"rejected by {self.name}",
            rule_name=self.name,
        )


def test_chain_needs_rules() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        ValidationChain([])


def test_all_rules_pass_gives_valid_verdict(make_proposal: ProposalFactory) -> None:
    chain = ValidationChain([_FakeRule("a"), _FakeRule("b")])

    verdict = chain.validate(make_proposal(proposal_id="P-1"))

    assert verdict == ValidationVerdict(proposal_id="P-1", valid=True)


def test_first_rejection_wins_and_stops_the_chain(make_proposal: ProposalFactory) -> None:
    first = _FakeRule("first", RejectionReason.SYNTAX_ERROR)
    second = _FakeRule("second", RejectionReason.IMPORT_ERROR)

    verdict = ValidationChain([first, second]).validate(make_proposal())

    assert verdict.reason is RejectionReason.SYNTAX_ERROR
    assert verdict.rule_name == "first"
    assert second.calls == []


def test_rules_run_in_the_given_order(make_proposal: ProposalFactory) -> None:
    passing = _FakeRule("passing")
    rejecting = _FakeRule("rejecting", RejectionReason.IMPORT_ERROR)
    chain = ValidationChain([passing, rejecting])

    verdict = chain.validate(make_proposal())

    assert chain.rule_names == ("passing", "rejecting")
    assert passing.calls == ["P-WM-02"]
    assert verdict.reason is RejectionReason.IMPORT_ERROR


def test_validate_all_keeps_rejected_proposals(make_proposal: ProposalFactory) -> None:
    chain = ValidationChain([SyntaxRule()])
    proposals = [make_proposal(proposal_id="ok"), make_proposal("def f(:\n", "broken")]

    verdicts = chain.validate_all(proposals)

    assert [(v.proposal_id, v.valid) for v in verdicts] == [("ok", True), ("broken", False)]


def test_real_chain_accepts_valid_file_and_rejects_broken_ones(
    make_proposal: ProposalFactory,
) -> None:
    chain = ValidationChain([SyntaxRule(), ImportRule(search_paths=[REFERENCE_DIR])])

    valid = chain.validate(make_proposal(proposal_id="valid"))
    broken_syntax = chain.validate(make_proposal("def test_x(:\n", "syntax"))
    broken_import = chain.validate(make_proposal("import missing_module\n", "import"))

    assert valid.valid is True
    assert broken_syntax.reason is RejectionReason.SYNTAX_ERROR
    assert broken_import.reason is RejectionReason.IMPORT_ERROR
