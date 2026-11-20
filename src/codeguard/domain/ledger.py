"""Proposal ledger: one immutable entry per proposal, valid or rejected (CG-12).

The ledger keeps every proposal (template, Groq or defective seed), so the validity
rate is always computed over the full denominator: rejected proposals are never dropped.
"""

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .models import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict

_SHA256_HEX_LENGTH = 64


class ProposalStatus(StrEnum):
    """Final validation status of a proposal in the ledger."""

    VALID = "valid"
    REJECTED = "rejected"


@dataclass(frozen=True)
class LedgerEntry:
    """Traceable record of one proposal and its validation verdict."""

    proposal_id: str
    case_ids: tuple[str, ...]
    source: ProposalSourceKind
    target: str
    file_name: str
    status: ProposalStatus
    reason: RejectionReason | None
    detail: str
    rule_name: str
    code_sha256: str

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("proposal_id must not be empty")
        if (self.status is ProposalStatus.REJECTED) != (self.reason is not None):
            raise ValueError("a rejected entry needs a reason and a valid entry must not have one")
        if len(self.code_sha256) != _SHA256_HEX_LENGTH:
            raise ValueError("code_sha256 must be a SHA-256 hex digest")

    @classmethod
    def from_validation(cls, proposal: TestProposal, verdict: ValidationVerdict) -> "LedgerEntry":
        """Combine a proposal with its verdict; ``code_sha256`` identifies the final version."""
        if proposal.proposal_id != verdict.proposal_id:
            raise ValueError(
                f"verdict {verdict.proposal_id!r} does not belong to proposal "
                f"{proposal.proposal_id!r}"
            )
        return cls(
            proposal_id=proposal.proposal_id,
            case_ids=tuple(proposal.case_ids),
            source=proposal.source,
            target=proposal.target_qualified_name,
            file_name=proposal.file_name,
            status=ProposalStatus.VALID if verdict.valid else ProposalStatus.REJECTED,
            reason=verdict.reason,
            detail=verdict.detail,
            rule_name=verdict.rule_name,
            code_sha256=hashlib.sha256(proposal.code.encode("utf-8")).hexdigest(),
        )

    def to_record(self) -> dict[str, object]:
        """Return a JSON-serialisable dict with a stable key order."""
        return {
            "proposal_id": self.proposal_id,
            "case_ids": list(self.case_ids),
            "source": self.source.value,
            "target": self.target,
            "file_name": self.file_name,
            "status": self.status.value,
            "reason": self.reason.value if self.reason else None,
            "detail": self.detail,
            "rule_name": self.rule_name,
            "code_sha256": self.code_sha256,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "LedgerEntry":
        """Rebuild an entry from ``to_record`` output; raises ValueError if malformed."""
        reason = record.get("reason")
        case_ids = record.get("case_ids")
        if not isinstance(case_ids, list) or not all(isinstance(c, str) for c in case_ids):
            raise ValueError("case_ids must be a list of strings")
        return cls(
            proposal_id=_text(record, "proposal_id"),
            case_ids=tuple(case_ids),
            source=ProposalSourceKind(_text(record, "source")),
            target=_text(record, "target"),
            file_name=_text(record, "file_name"),
            status=ProposalStatus(_text(record, "status")),
            reason=RejectionReason(reason) if isinstance(reason, str) else None,
            detail=_text(record, "detail"),
            rule_name=_text(record, "rule_name"),
            code_sha256=_text(record, "code_sha256"),
        )


def _text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError(f"ledger field {key!r} must be a string")
    return value


@dataclass(frozen=True)
class LedgerSummary:
    """Proposed vs. valid counts over the full ledger (explicit denominator)."""

    total: int
    valid: int
    rejected: int
    by_reason: Mapping[str, int]
    by_source: Mapping[str, int]
    valid_by_source: Mapping[str, int]

    @classmethod
    def from_entries(cls, entries: Iterable[LedgerEntry]) -> "LedgerSummary":
        """Count proposals, valid ones and rejection reasons."""
        items = tuple(entries)
        valid = [entry for entry in items if entry.status is ProposalStatus.VALID]
        reasons = Counter(entry.reason.value for entry in items if entry.reason is not None)
        return cls(
            total=len(items),
            valid=len(valid),
            rejected=len(items) - len(valid),
            by_reason=_frozen_counts(reasons),
            by_source=_frozen_counts(Counter(entry.source.value for entry in items)),
            valid_by_source=_frozen_counts(Counter(entry.source.value for entry in valid)),
        )

    @property
    def validity_pct(self) -> float:
        """Valid proposals over all proposals, in percent (0.0 for an empty ledger)."""
        if self.total == 0:
            return 0.0
        return self.valid / self.total * 100.0


def _frozen_counts(counts: Counter[str]) -> Mapping[str, int]:
    return MappingProxyType(dict(sorted(counts.items())))
