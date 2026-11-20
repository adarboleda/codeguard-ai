"""Tests for ImportRule (CG-09). Each check starts a real Python subprocess."""

from pathlib import Path

import pytest
from conftest import REFERENCE_DIR, ProposalFactory

from codeguard.adapters.validation import ImportRule
from codeguard.domain import RejectionReason


@pytest.fixture
def rule() -> ImportRule:
    return ImportRule(search_paths=[REFERENCE_DIR])


def test_valid_proposal_imports(rule: ImportRule, make_proposal: ProposalFactory) -> None:
    assert rule.check(make_proposal()) is None


def test_unknown_module_is_rejected(rule: ImportRule, make_proposal: ProposalFactory) -> None:
    verdict = rule.check(make_proposal(code="import sciref_does_not_exist\n"))

    assert verdict is not None
    assert verdict.valid is False
    assert verdict.reason is RejectionReason.IMPORT_ERROR
    assert verdict.rule_name == "import"
    assert "ModuleNotFoundError" in verdict.detail


def test_unknown_name_in_sciref_is_rejected(
    rule: ImportRule, make_proposal: ProposalFactory
) -> None:
    verdict = rule.check(make_proposal(code="from sciref.numeric import geometric_mean\n"))

    assert verdict is not None
    assert verdict.reason is RejectionReason.IMPORT_ERROR
    assert "ImportError" in verdict.detail


def test_module_level_exception_is_rejected(
    rule: ImportRule, make_proposal: ProposalFactory
) -> None:
    verdict = rule.check(make_proposal(code="raise RuntimeError('boom at import time')\n"))

    assert verdict is not None
    assert verdict.reason is RejectionReason.IMPORT_ERROR
    assert "RuntimeError: boom at import time" in verdict.detail


def test_main_block_is_not_executed(rule: ImportRule, make_proposal: ProposalFactory) -> None:
    code = "if __name__ == '__main__':\n    raise SystemExit(1)\n"

    assert rule.check(make_proposal(code=code)) is None


def test_sciref_is_not_found_without_search_path(make_proposal: ProposalFactory) -> None:
    verdict = ImportRule().check(make_proposal())

    assert verdict is not None
    assert verdict.reason is RejectionReason.IMPORT_ERROR
    assert "sciref" in verdict.detail


def test_slow_import_is_rejected_by_timeout(make_proposal: ProposalFactory) -> None:
    rule = ImportRule(search_paths=[REFERENCE_DIR], timeout_seconds=1.0)

    verdict = rule.check(make_proposal(code="import time\ntime.sleep(30)\n"))

    assert verdict is not None
    assert verdict.reason is RejectionReason.IMPORT_ERROR
    assert verdict.detail == "timeout after 1 s"


def test_unsafe_file_name_falls_back(rule: ImportRule, make_proposal: ProposalFactory) -> None:
    assert rule.check(make_proposal(file_name="../../escape.py")) is None


def test_existing_pythonpath_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_proposal: ProposalFactory
) -> None:
    (tmp_path / "team_helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    rule = ImportRule(search_paths=[REFERENCE_DIR])

    code = "import team_helpers\nfrom sciref.numeric import clamp\n"

    assert rule.check(make_proposal(code=code)) is None


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        ImportRule(timeout_seconds=0)
