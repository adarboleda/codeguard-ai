"""Validation chain: applies the rules in order and stops at the first rejection."""

from collections.abc import Iterable, Sequence

from codeguard.domain import TestProposal, ValidationVerdict
from codeguard.ports.validation import ValidationRule


class ValidationChain:
    """Chain of Responsibility over ``ValidationRule`` objects.

    The order of ``rules`` is the order of the plan (section 2.1): syntax, import,
    target function, useful assertions, pytest collection. The first rule that rejects
    a proposal decides its rejection reason; later rules are not evaluated.
    """

    def __init__(self, rules: Sequence[ValidationRule]) -> None:
        if not rules:
            raise ValueError("ValidationChain needs at least one rule")
        self._rules: tuple[ValidationRule, ...] = tuple(rules)

    @property
    def rule_names(self) -> tuple[str, ...]:
        """Names of the rules in evaluation order."""
        return tuple(rule.name for rule in self._rules)

    def validate(self, proposal: TestProposal) -> ValidationVerdict:
        """Return the first rejection produced by a rule, or a valid verdict."""
        for rule in self._rules:
            verdict = rule.check(proposal)
            if verdict is not None and not verdict.valid:
                return verdict
        return ValidationVerdict(proposal_id=proposal.proposal_id, valid=True)

    def validate_all(self, proposals: Iterable[TestProposal]) -> tuple[ValidationVerdict, ...]:
        """Validate every proposal; rejected ones are kept, never dropped."""
        return tuple(self.validate(proposal) for proposal in proposals)
