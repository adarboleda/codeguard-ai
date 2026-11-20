"""Shared fixtures for the validation chain tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from codeguard.domain import ProposalSourceKind, TestProposal

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "reference"

VALID_PROPOSAL_CODE = """\
import pytest

from sciref.numeric import weighted_mean


def test_weighted_mean_wm_02() -> None:
    assert weighted_mean([1, 3], [1, 3]) == pytest.approx(2.5, rel=1e-9)
"""

ProposalFactory = Callable[..., TestProposal]


@pytest.fixture
def make_proposal() -> ProposalFactory:
    """Build a TestProposal (weighted_mean by default) with the given code."""

    def _make(
        code: str = VALID_PROPOSAL_CODE,
        proposal_id: str = "P-WM-02",
        file_name: str = "test_weighted_mean_wm_02.py",
        target_module: str = "sciref.numeric",
        target_function: str = "weighted_mean",
        source: ProposalSourceKind = ProposalSourceKind.TEMPLATE,
    ) -> TestProposal:
        return TestProposal(
            proposal_id=proposal_id,
            target_module=target_module,
            target_function=target_function,
            source=source,
            code=code,
            case_ids=("WM-02",),
            file_name=file_name,
        )

    return _make
