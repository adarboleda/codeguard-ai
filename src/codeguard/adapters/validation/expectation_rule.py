"""Last rule of the validation chain: LLM tests must pass on the original code (CG-31).

The LLM is not the oracle (plan, section 2.4). A test it proposed that fails against the
original ``sciref`` asserts a wrong expected value, so it is rejected with
``WRONG_EXPECTATION`` and still counted in the denominator. Template proposals skip this
rule: their expected values come from the hand-made oracle of ``contracts.yaml``.
"""

import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from codeguard.domain import ProposalSourceKind, RejectionReason, TestProposal, ValidationVerdict
from codeguard.domain.execution import ExecutionOutcome, SuiteResult
from codeguard.ports.execution import SuiteRunner

_SAFE_FILE_NAME = re.compile(r"^test_\w+\.py$", re.ASCII)
_MAX_DETAIL_CHARS = 300


class ExpectationRule:
    """Runs each proposal of the given sources once against the original package."""

    name = "expectation"

    def __init__(
        self,
        runner: SuiteRunner,
        reference_dir: Path,
        sources: Iterable[ProposalSourceKind] = (ProposalSourceKind.GROQ,),
    ) -> None:
        self._runner = runner
        self._reference_dir = reference_dir
        self._sources = frozenset(sources)

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """``None`` if the proposal's tests pass on the original code."""
        if proposal.source not in self._sources:
            return None
        with tempfile.TemporaryDirectory(prefix="codeguard-expect-") as tmp:
            name = proposal.file_name if _SAFE_FILE_NAME.match(proposal.file_name) else "test_x.py"
            path = Path(tmp) / name
            path.write_text(proposal.code, encoding="utf-8")
            result = self._runner.run([path], self._reference_dir, Path(tmp) / "out")
        if result.is_green:
            return None
        reason, detail = _diagnose(result)
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=reason,
            detail=detail[:_MAX_DETAIL_CHARS],
            rule_name=self.name,
        )


def _diagnose(result: SuiteResult) -> tuple[RejectionReason, str]:
    if result.timed_out:
        return RejectionReason.WRONG_EXPECTATION, result.detail
    if result.failed:
        test = next(t for t in result.failing_tests if t.outcome is ExecutionOutcome.FAILED)
        return RejectionReason.WRONG_EXPECTATION, f"{test.node_id}: {test.message}"
    if result.errors:
        test = result.failing_tests[0]
        return RejectionReason.COLLECTION_ERROR, f"{test.node_id}: {test.message}"
    return RejectionReason.COLLECTION_ERROR, result.detail or "pytest collected no tests"
