"""Domain layer exports for CodeGuard AI."""

from .errors import CodeGuardError, SpecError
from .models import (
    CaseKind,
    ContractCase,
    Finding,
    FunctionContract,
    Mutant,
    MutantResult,
    MutantStatus,
    ProposalSourceKind,
    RejectionReason,
    RunMetrics,
    Severity,
    TestProposal,
    ValidationVerdict,
)

__all__ = [
    "CaseKind",
    "CodeGuardError",
    "ContractCase",
    "Finding",
    "FunctionContract",
    "Mutant",
    "MutantResult",
    "MutantStatus",
    "ProposalSourceKind",
    "RejectionReason",
    "RunMetrics",
    "Severity",
    "SpecError",
    "TestProposal",
    "ValidationVerdict",
]
