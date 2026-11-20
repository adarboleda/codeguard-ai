"""Port for the rules of the proposal validation chain (Chain of Responsibility)."""

from typing import Protocol

from codeguard.domain import TestProposal, ValidationVerdict


class ValidationRule(Protocol):
    """One link of the validation chain.

    A rule inspects a single proposal and returns ``None`` when the proposal passes,
    or a rejected ``ValidationVerdict`` (``valid=False`` with its ``RejectionReason``)
    when it does not. Rules never raise for a bad proposal: rejecting is their job.
    """

    @property
    def name(self) -> str:
        """Short identifier stored in ``ValidationVerdict.rule_name``."""
        ...

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """Return ``None`` if the proposal passes this rule, else a rejection."""
        ...
