"""``GroqProposalSource``: a second ProposalSource (Strategy) backed by an LLM (CG-31).

One call per function. The answer is split into one proposal per test function and
every proposal goes through the same validation chain as the template ones. A failed
call becomes a GENERATION_ERROR placeholder, so it is counted, never hidden.
"""

import re
from collections.abc import Sequence
from pathlib import Path

from codeguard.adapters.llm.prompt import build_prompt, read_docstring
from codeguard.adapters.llm.records import write_record
from codeguard.adapters.llm.response import extract_code, split_tests
from codeguard.domain import FunctionContract, ProposalSourceKind, TestProposal
from codeguard.domain.llm import GENERATION_ERROR_MARKER, LlmError, LlmPrompt, LlmReply
from codeguard.ports.llm import LlmClient

DEFAULT_MAX_TESTS_PER_FUNCTION = 8
_UNSAFE = re.compile(r"\W")


class GroqProposalSource:
    """Proposes tests for each contract from the model's answer (live or replayed)."""

    def __init__(
        self,
        client: LlmClient,
        llm_dir: Path,
        reference_dir: Path,
        *,
        max_tests_per_function: int = DEFAULT_MAX_TESTS_PER_FUNCTION,
        temperature: float = 0.0,
        base_url: str = "",
        replayed_from: str | None = None,
    ) -> None:
        if max_tests_per_function < 1:
            raise ValueError("max_tests_per_function must be at least 1")
        self._client = client
        self._llm_dir = llm_dir
        self._reference_dir = reference_dir
        self._max_tests = max_tests_per_function
        self._temperature = temperature
        self._base_url = base_url
        self._replayed_from = replayed_from

    def generate(self, contracts: Sequence[FunctionContract]) -> tuple[TestProposal, ...]:
        """Exactly one model call per contract, in contract order."""
        return tuple(proposal for c in contracts for proposal in self._for_contract(c))

    def _for_contract(self, contract: FunctionContract) -> list[TestProposal]:
        docstring = read_docstring(self._reference_dir, contract)
        prompt = build_prompt(contract, docstring, max_tests=self._max_tests)
        try:
            reply = self._client.complete(contract.qualified_name, prompt)
        except LlmError as error:
            self._record(contract, prompt, LlmReply("", self._client.model), error=str(error))
            return [_generation_error(contract, str(error))]
        self._record(contract, prompt, reply, error=None)
        modules = split_tests(extract_code(reply.text), self._max_tests)
        return [_proposal(contract, index, code) for index, code in enumerate(modules, start=1)]

    def _record(
        self, contract: FunctionContract, prompt: LlmPrompt, reply: LlmReply, error: str | None
    ) -> None:
        write_record(
            self._llm_dir,
            function=contract.qualified_name,
            prompt=prompt,
            model=reply.model,
            temperature=self._temperature,
            base_url=self._base_url,
            response=None if error is not None else reply.text,
            error=error,
            usage=reply.usage,
            replayed_from=self._replayed_from,
        )


def _slug(contract: FunctionContract) -> str:
    return _UNSAFE.sub("_", contract.name).lower()


def _proposal(contract: FunctionContract, index: int, code: str) -> TestProposal:
    slug = _slug(contract)
    return TestProposal(
        proposal_id=f"groq-{slug}-{index:02d}",
        target_module=contract.module,
        target_function=contract.name,
        source=ProposalSourceKind.GROQ,
        code=code,
        file_name=f"test_groq_{slug}_{index:02d}.py",
    )


def _generation_error(contract: FunctionContract, detail: str) -> TestProposal:
    slug = _slug(contract)
    one_line = " ".join(detail.split())
    return TestProposal(
        proposal_id=f"groq-{slug}-error",
        target_module=contract.module,
        target_function=contract.name,
        source=ProposalSourceKind.GROQ,
        code=f"{GENERATION_ERROR_MARKER} {one_line}\n",
        file_name=f"test_groq_{slug}_error.py",
    )
