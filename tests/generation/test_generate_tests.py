"""Tests for GenerateTests use case and FileProposalWriter (CG-07)."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from codeguard.adapters.generation import FileProposalWriter
from codeguard.application.generate_tests import GenerateTests
from codeguard.domain import (
    CaseKind,
    ContractCase,
    FunctionContract,
    ProposalSourceKind,
    TestProposal,
)


class _StubSpecRepository:
    def __init__(self, contracts: Sequence[FunctionContract]) -> None:
        self._contracts = tuple(contracts)

    def load(self) -> tuple[FunctionContract, ...]:
        return self._contracts


class _StubProposalSource:
    def __init__(self, proposals: Sequence[TestProposal]) -> None:
        self._proposals = tuple(proposals)
        self.received_contracts: tuple[FunctionContract, ...] = ()

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        self.received_contracts = tuple(contracts)
        return self._proposals


def _sample_contract() -> FunctionContract:
    return FunctionContract(
        module="sciref.numeric",
        name="clamp",
        signature="clamp(x, lo, hi)",
        docstring="Clamp",
        cases=(
            ContractCase(
                case_id="CL-01",
                kind=CaseKind.NORMAL,
                description="in range",
                inputs={"x": 5, "lo": 0, "hi": 10},
                expected=5,
            ),
        ),
    )


def _sample_proposal(proposal_id: str = "tpl-1", file_name: str = "test_one.py") -> TestProposal:
    return TestProposal(
        proposal_id=proposal_id,
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code="def test_one() -> None:\n    assert 1 == 1\n",
        case_ids=("CL-01",),
        file_name=file_name,
    )


def test_generate_tests_writes_proposals_to_run_dir(tmp_path: Path) -> None:
    contracts = (_sample_contract(),)
    proposals = (_sample_proposal("p-1", "test_clamp_cl_01.py"),)
    source = _StubProposalSource(proposals)
    use_case = GenerateTests(
        spec_repository=_StubSpecRepository(contracts),
        proposal_source=source,
        proposal_writer=FileProposalWriter(),
    )

    report = use_case.execute(tmp_path / "run-01")

    assert source.received_contracts == contracts
    assert report.proposals == proposals
    assert report.proposals_dir == tmp_path / "run-01" / "proposals"
    assert report.written_paths == (report.proposals_dir / "test_clamp_cl_01.py",)
    assert report.written_paths[0].read_text(encoding="utf-8") == proposals[0].code


def test_generate_tests_rejects_duplicate_proposal_ids(tmp_path: Path) -> None:
    proposals = (
        _sample_proposal("dup-id", "test_one.py"),
        _sample_proposal("dup-id", "test_two.py"),
    )
    use_case = GenerateTests(
        spec_repository=_StubSpecRepository((_sample_contract(),)),
        proposal_source=_StubProposalSource(proposals),
        proposal_writer=FileProposalWriter(),
    )

    with pytest.raises(ValueError, match="duplicate proposal_id"):
        use_case.execute(tmp_path / "run-02")


def test_file_writer_rejects_unsafe_or_duplicate_file_names(tmp_path: Path) -> None:
    writer = FileProposalWriter()
    escape_batch = [_sample_proposal("p-1", "../escape.py")]
    empty_name_batch = [_sample_proposal("p-1", "")]
    duplicate_batch = [
        _sample_proposal("p-1", "test_same.py"),
        _sample_proposal("p-2", "test_same.py"),
    ]

    with pytest.raises(ValueError, match="unsafe proposal file_name"):
        writer.write(escape_batch, tmp_path)

    with pytest.raises(ValueError, match="unsafe proposal file_name"):
        writer.write(empty_name_batch, tmp_path)

    with pytest.raises(ValueError, match="duplicate proposal file_name"):
        writer.write(duplicate_batch, tmp_path)
