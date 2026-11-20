"""Tests for the ledger domain model: LedgerEntry and LedgerSummary (CG-12)."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest

from codeguard.domain import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.ledger import LedgerEntry, LedgerSummary, ProposalStatus

CODE = "def test_x() -> None:\n    assert 1 == 1\n"


def _proposal(proposal_id: str = "P-1", source: ProposalSourceKind = ProposalSourceKind.TEMPLATE):
    return TestProposal(
        proposal_id=proposal_id,
        target_module="sciref.numeric",
        target_function="clamp",
        source=source,
        code=CODE,
        case_ids=("CL-01", "CL-02"),
        file_name="test_clamp.py",
    )


def _rejected(proposal_id: str = "P-1", reason: RejectionReason = RejectionReason.SYNTAX_ERROR):
    return ValidationVerdict(proposal_id, False, reason, "line 1: invalid syntax", "syntax")


def test_valid_entry_from_validation() -> None:
    entry = LedgerEntry.from_validation(_proposal(), ValidationVerdict("P-1", True))

    assert entry.status is ProposalStatus.VALID
    assert entry.reason is None
    assert entry.target == "sciref.numeric.clamp"
    assert entry.case_ids == ("CL-01", "CL-02")
    assert entry.code_sha256 == hashlib.sha256(CODE.encode("utf-8")).hexdigest()


def test_rejected_entry_keeps_reason_detail_and_rule() -> None:
    entry = LedgerEntry.from_validation(_proposal(), _rejected())

    assert entry.status is ProposalStatus.REJECTED
    assert entry.reason is RejectionReason.SYNTAX_ERROR
    assert (entry.detail, entry.rule_name) == ("line 1: invalid syntax", "syntax")


def test_verdict_of_another_proposal_is_refused() -> None:
    with pytest.raises(ValueError, match="does not belong"):
        LedgerEntry.from_validation(_proposal("P-1"), ValidationVerdict("P-2", True))


def test_entry_is_immutable() -> None:
    entry = LedgerEntry.from_validation(_proposal(), ValidationVerdict("P-1", True))

    with pytest.raises(FrozenInstanceError):
        entry.detail = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"proposal_id": " "}, "proposal_id"),
        ({"reason": RejectionReason.SYNTAX_ERROR}, "rejected entry needs a reason"),
        ({"code_sha256": "abc"}, "SHA-256"),
    ],
)
def test_invariants(changes: dict[str, Any], message: str) -> None:
    entry = LedgerEntry.from_validation(_proposal(), ValidationVerdict("P-1", True))

    with pytest.raises(ValueError, match=message):
        replace(entry, **changes)


def test_record_round_trip_is_json_safe() -> None:
    entry = LedgerEntry.from_validation(_proposal(), _rejected())

    record = json.loads(json.dumps(entry.to_record()))

    assert list(record) == [
        "proposal_id",
        "case_ids",
        "source",
        "target",
        "file_name",
        "status",
        "reason",
        "detail",
        "rule_name",
        "code_sha256",
    ]
    assert (record["source"], record["status"], record["reason"]) == (
        "template",
        "rejected",
        "SYNTAX_ERROR",
    )
    assert LedgerEntry.from_record(record) == entry


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("case_ids", "CL-01", "case_ids"),
        ("proposal_id", 7, "proposal_id"),
        ("source", "unknown", "unknown"),
    ],
)
def test_malformed_record_is_refused(field: str, value: object, message: str) -> None:
    record = LedgerEntry.from_validation(_proposal(), _rejected()).to_record()
    record[field] = value

    with pytest.raises(ValueError, match=message):
        LedgerEntry.from_record(record)


def test_summary_counts_with_explicit_denominator() -> None:
    entries = [
        LedgerEntry.from_validation(_proposal("t1"), ValidationVerdict("t1", True)),
        LedgerEntry.from_validation(_proposal("t2"), ValidationVerdict("t2", True)),
        LedgerEntry.from_validation(_proposal("t3"), _rejected("t3")),
        LedgerEntry.from_validation(
            _proposal("g1", ProposalSourceKind.GROQ),
            _rejected("g1", RejectionReason.WRONG_EXPECTATION),
        ),
    ]

    summary = LedgerSummary.from_entries(entries)

    assert (summary.total, summary.valid, summary.rejected) == (4, 2, 2)
    assert summary.validity_pct == pytest.approx(50.0)
    assert dict(summary.by_reason) == {"SYNTAX_ERROR": 1, "WRONG_EXPECTATION": 1}
    assert dict(summary.by_source) == {"groq": 1, "template": 3}
    assert dict(summary.valid_by_source) == {"template": 2}


def test_empty_summary() -> None:
    summary = LedgerSummary.from_entries([])

    assert (summary.total, summary.valid, summary.validity_pct) == (0, 0, 0.0)
