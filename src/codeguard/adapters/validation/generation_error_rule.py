"""Rule 0 of the validation chain: a failed LLM call is a GENERATION_ERROR (CG-31).

When the model gives no usable answer, the source writes a placeholder proposal whose
first line carries ``GENERATION_ERROR_MARKER``. Rejecting it here keeps the failed call
in the ledger and in the validity denominator instead of silently dropping it.
"""

from codeguard.domain import RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.llm import GENERATION_ERROR_MARKER


class GenerationErrorRule:
    """Rejects placeholder proposals that stand for a failed generation."""

    name = "generation"

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        first_line = proposal.code.lstrip().split("\n", 1)[0]
        if not first_line.startswith(GENERATION_ERROR_MARKER):
            return None
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=RejectionReason.GENERATION_ERROR,
            detail=first_line.removeprefix(GENERATION_ERROR_MARKER).strip(),
            rule_name=self.name,
        )
