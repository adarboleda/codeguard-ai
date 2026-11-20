"""Rule 1 of the validation chain: the proposal must be valid Python (CG-09)."""

import ast

from codeguard.domain import RejectionReason, TestProposal, ValidationVerdict

_FALLBACK_FILE_NAME = "<proposal>"


class SyntaxRule:
    """Rejects proposals that do not parse or do not compile.

    ``ast.parse`` alone is not enough: some errors are only detected by the compiler,
    for example ``return`` outside a function or ``nonlocal`` at module level.
    """

    name = "syntax"

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """Return ``None`` if the code parses and compiles, else ``SYNTAX_ERROR``."""
        file_name = proposal.file_name or _FALLBACK_FILE_NAME
        try:
            tree = ast.parse(proposal.code, filename=file_name)
            compile(tree, file_name, "exec")
        except SyntaxError as error:
            return self._reject(proposal, f"line {error.lineno}: {error.msg}")
        except (MemoryError, RecursionError) as error:
            # The parser raises these for absurdly nested code ("Parser stack overflowed");
            # a bad proposal must be rejected, never crash the pipeline.
            return self._reject(proposal, f"source too complex to parse: {error}")
        return None

    def _reject(self, proposal: TestProposal, detail: str) -> ValidationVerdict:
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=RejectionReason.SYNTAX_ERROR,
            detail=detail,
            rule_name=self.name,
        )
