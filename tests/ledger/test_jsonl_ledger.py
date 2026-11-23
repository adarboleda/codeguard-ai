"""Tests for the JSON Lines ledger adapter (CG-12)."""

from pathlib import Path

import pytest

from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.domain import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.ledger import LedgerEntry


def _entry(proposal_id: str, valid: bool) -> LedgerEntry:
    proposal = TestProposal(
        proposal_id=proposal_id,
        target_module="sciref.signals",
        target_function="moving_average",
        source=ProposalSourceKind.TEMPLATE,
        code=f"# {proposal_id}: ventana móvil\n",
        case_ids=("MA-01",),
        file_name=f"test_{proposal_id}.py",
    )
    reason = None if valid else RejectionReason.NO_ASSERTION
    detail = "" if valid else "falta aserción útil"
    verdict = ValidationVerdict(proposal_id, valid, reason, detail)
    return LedgerEntry.from_validation(proposal, verdict)


def test_write_creates_run_dir_and_one_line_per_entry(tmp_path: Path) -> None:
    entries = [_entry("a", True), _entry("b", False), _entry("c", True)]
    run_dir = tmp_path / "out" / "run-20261120"

    path = JsonlLedger().write(entries, run_dir)

    assert path == run_dir / LEDGER_FILE_NAME
    raw = path.read_bytes()
    assert raw.count(b"\n") == 3
    assert b"\r\n" not in raw
    assert "falta aserción útil".encode() in raw  # UTF-8, not \\u escapes


def test_round_trip_preserves_entries_and_order(tmp_path: Path) -> None:
    entries = (_entry("b", False), _entry("a", True))
    ledger = JsonlLedger()

    assert ledger.read(ledger.write(entries, tmp_path)) == entries


def test_empty_ledger(tmp_path: Path) -> None:
    ledger = JsonlLedger()

    path = ledger.write([], tmp_path)

    assert path.read_text(encoding="utf-8") == ""
    assert ledger.read(path) == ()


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    ledger = JsonlLedger()
    path = ledger.write([_entry("a", True)], tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    assert len(ledger.read(path)) == 1


@pytest.mark.parametrize("bad_line", ["{not json", "[1, 2]", '{"proposal_id": "x"}'])
def test_malformed_line_reports_file_and_line(tmp_path: Path, bad_line: str) -> None:
    ledger = JsonlLedger()
    path = ledger.write([_entry("a", True)], tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + bad_line + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=f"{LEDGER_FILE_NAME}:2: invalid ledger line"):
        ledger.read(path)


def test_missing_ledger_file_has_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"ledger not found.*codeguard validate"):
        JsonlLedger().read(tmp_path / LEDGER_FILE_NAME)
