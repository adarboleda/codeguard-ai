"""Tests for the ValidateProposals use case: chain + ledger (CG-12)."""

import json
from pathlib import Path

import pytest
from conftest import REFERENCE_DIR, ProposalFactory

from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.adapters.validation import AssertionRule, ImportRule, SyntaxRule, TargetRule
from codeguard.application.validate_proposals import ValidateProposals
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import FunctionContract, ProposalSourceKind, RejectionReason
from codeguard.domain.ledger import ProposalStatus

WEIGHTED_MEAN = FunctionContract(
    module="sciref.numeric",
    name="weighted_mean",
    signature="weighted_mean(values, weights)",
    docstring="Σ(w·v) / Σw",
)


def _in_test(imports: str, call: str) -> str:
    """Put the call inside a test function, so it does not run at import time."""
    return f"{imports}\n\n\ndef test_x() -> None:\n    assert {call} == 1\n"


@pytest.fixture
def use_case() -> ValidateProposals:
    chain = ValidationChain(
        [
            SyntaxRule(),
            ImportRule(search_paths=[REFERENCE_DIR]),
            TargetRule([WEIGHTED_MEAN]),
            AssertionRule(),
        ]
    )
    return ValidateProposals(chain, JsonlLedger())


def test_ledger_keeps_every_proposal_with_its_reason(
    use_case: ValidateProposals, make_proposal: ProposalFactory, tmp_path: Path
) -> None:
    proposals = [
        make_proposal(proposal_id="valid"),
        make_proposal("def test_x(:\n", "seed-syntax", source=ProposalSourceKind.DEFECTIVE_SEED),
        make_proposal("import missing_module\n", "bad-import"),
        make_proposal(
            _in_test("from sciref.numeric import clamp", "clamp(1, 0, 2)"), "wrong-target"
        ),
        make_proposal(
            _in_test("from sciref.numeric import weighted_mean", "weighted_mean([1])"),
            "bad-args",
            source=ProposalSourceKind.GROQ,
        ),
        make_proposal(
            "from sciref.numeric import weighted_mean\n\n\n"
            "def test_seed() -> None:\n    weighted_mean([1], [1])\n    assert True\n",
            "seed-tautological",
            source=ProposalSourceKind.DEFECTIVE_SEED,
        ),
    ]

    report = use_case.execute(proposals, tmp_path / "run-001")

    assert report.ledger_path == tmp_path / "run-001" / LEDGER_FILE_NAME
    assert [entry.proposal_id for entry in report.entries] == [p.proposal_id for p in proposals]
    assert [entry.reason for entry in report.entries] == [
        None,
        RejectionReason.SYNTAX_ERROR,
        RejectionReason.IMPORT_ERROR,
        RejectionReason.TARGET_NOT_CALLED,
        RejectionReason.INVALID_SIGNATURE,
        RejectionReason.TAUTOLOGICAL_ASSERTION,
    ]
    assert report.entries[0].status is ProposalStatus.VALID
    assert (report.summary.total, report.summary.valid, report.summary.rejected) == (6, 1, 5)
    assert report.summary.validity_pct == pytest.approx(100 / 6)
    assert dict(report.summary.by_source) == {"defective_seed": 2, "groq": 1, "template": 3}


def test_ledger_file_has_one_json_line_per_proposal(
    use_case: ValidateProposals, make_proposal: ProposalFactory, tmp_path: Path
) -> None:
    proposals = [make_proposal(proposal_id="a"), make_proposal("def f(:\n", "b")]

    report = use_case.execute(proposals, tmp_path)

    lines = report.ledger_path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [(r["proposal_id"], r["status"], r["reason"]) for r in records] == [
        ("a", "valid", None),
        ("b", "rejected", "SYNTAX_ERROR"),
    ]
    assert JsonlLedger().read(report.ledger_path) == report.entries


def test_duplicate_proposal_ids_are_refused(
    use_case: ValidateProposals, make_proposal: ProposalFactory, tmp_path: Path
) -> None:
    proposals = [make_proposal(proposal_id="same"), make_proposal(proposal_id="same")]

    with pytest.raises(ValueError, match="duplicate proposal_id in batch: same"):
        use_case.execute(proposals, tmp_path)
