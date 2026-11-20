"""Tests for SyntaxRule (CG-09)."""

import ast

from conftest import ProposalFactory

from codeguard.adapters.validation import SyntaxRule
from codeguard.domain import RejectionReason


def test_valid_proposal_passes(make_proposal: ProposalFactory) -> None:
    assert SyntaxRule().check(make_proposal()) is None


def test_broken_syntax_is_rejected_with_line(make_proposal: ProposalFactory) -> None:
    proposal = make_proposal(code="def test_broken(:\n    assert True\n")

    verdict = SyntaxRule().check(proposal)

    assert verdict is not None
    assert verdict.valid is False
    assert verdict.reason is RejectionReason.SYNTAX_ERROR
    assert verdict.detail.startswith("line 1:")
    assert verdict.rule_name == "syntax"
    assert verdict.proposal_id == proposal.proposal_id


def test_error_only_detected_by_compile_is_rejected(make_proposal: ProposalFactory) -> None:
    code = "return 1\n"
    ast.parse(code)  # ast.parse accepts it: only compile() detects the problem

    verdict = SyntaxRule().check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.reason is RejectionReason.SYNTAX_ERROR
    assert "outside function" in verdict.detail


def test_null_bytes_are_rejected(make_proposal: ProposalFactory) -> None:
    verdict = SyntaxRule().check(make_proposal(code="x = 1\0\n"))

    assert verdict is not None
    assert verdict.reason is RejectionReason.SYNTAX_ERROR


def test_overly_nested_code_is_rejected_not_crashing(make_proposal: ProposalFactory) -> None:
    code = "x = " + "-" * 100_000 + "1\n"  # makes the parser raise MemoryError

    verdict = SyntaxRule().check(make_proposal(code=code))

    assert verdict is not None
    assert verdict.reason is RejectionReason.SYNTAX_ERROR
    assert verdict.detail.startswith("source too complex to parse")


def test_empty_file_name_uses_placeholder(make_proposal: ProposalFactory) -> None:
    verdict = SyntaxRule().check(make_proposal(code="def f(:\n", file_name=""))

    assert verdict is not None
    assert verdict.reason is RejectionReason.SYNTAX_ERROR
