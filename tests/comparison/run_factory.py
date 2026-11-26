"""Builds the artifacts of a finished run, small and fast, for the comparison tests."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from codeguard.adapters.ledger import JsonlLedger
from codeguard.adapters.llm import write_record
from codeguard.domain import ProposalSourceKind, RejectionReason
from codeguard.domain.ledger import LedgerEntry, ProposalStatus
from codeguard.domain.llm import LlmPrompt

BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "openai/gpt-oss-120b"

# (proposal id, source, function, rejection reason or None when valid)
Proposal = tuple[str, ProposalSourceKind, str, RejectionReason | None]
# (covered lines, statements, covered branches, branches)
Coverage = tuple[int, int, int, int]


@dataclass(frozen=True)
class LlmCall:
    function: str
    tokens: int = 0
    failed: bool = False
    replayed_from: str | None = None


def make_run(
    out: Path,
    run_id: str,
    *,
    proposals: Sequence[Proposal],
    passed: int,
    mutants: Mapping[str, tuple[str, str]],
    failed: int = 0,
    coverage: Coverage | None = None,
    llm_calls: Sequence[LlmCall] = (),
    seed: int | None = None,
) -> Path:
    """Write the run's artifacts; ``mutants`` maps id -> (function, status)."""
    run_dir = out / run_id
    JsonlLedger().write([_entry(*proposal) for proposal in proposals], run_dir)
    (run_dir / "junit.xml").write_text(_junit(passed, failed), encoding="utf-8")
    if coverage is not None:
        _write_json(run_dir / "coverage.json", _coverage_json(coverage))
    if mutants:
        _write_json(run_dir / "mutants.json", [_mutant(*item) for item in _flat(mutants)])
    for call in llm_calls:
        _record(run_dir / "llm", call)
    if seed is not None:
        _write_json(run_dir / "run_config.json", {"run_id": run_id, "seed": seed})
    return run_dir


def _entry(
    proposal_id: str, source: ProposalSourceKind, function: str, reason: RejectionReason | None
) -> LedgerEntry:
    return LedgerEntry(
        proposal_id=proposal_id,
        case_ids=(),
        source=source,
        target=f"sciref.numeric.{function}",
        file_name=f"test_{proposal_id.replace('-', '_')}.py",
        status=ProposalStatus.VALID if reason is None else ProposalStatus.REJECTED,
        reason=reason,
        detail="" if reason is None else "detail",
        rule_name="" if reason is None else "rule",
        code_sha256="0" * 64,
    )


def _junit(passed: int, failed: int) -> str:
    cases = [
        f'<testcase classname="tests.t{i}" name="test_{i}" file="tests/t{i}.py" time="0.01"/>'
        for i in range(passed)
    ]
    cases += [
        f'<testcase classname="tests.f{i}" name="test_f{i}" file="tests/f{i}.py" time="0.01">'
        '<failure message="assert 1 == 2"/></testcase>'
        for i in range(failed)
    ]
    return f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>"


def _coverage_json(coverage: Coverage) -> dict[str, object]:
    covered, statements, covered_branches, branches = coverage
    summary = {
        "num_statements": statements,
        "covered_lines": covered,
        "num_branches": branches,
        "covered_branches": covered_branches,
    }
    return {"files": {"sciref/numeric.py": {"summary": summary, "missing_lines": []}}}


def _flat(mutants: Mapping[str, tuple[str, str]]) -> list[tuple[str, str, str]]:
    return [(mutant_id, function, status) for mutant_id, (function, status) in mutants.items()]


def _mutant(mutant_id: str, function: str, status: str) -> dict[str, object]:
    return {
        "mutant_id": mutant_id,
        "function": function,
        "status": status,
        "exit_code": 1,
        "timed_out": False,
        "failed": 1,
        "duration_seconds": 0.1,
    }


def _record(llm_dir: Path, call: LlmCall) -> None:
    write_record(
        llm_dir,
        function=f"sciref.numeric.{call.function}",
        prompt=LlmPrompt("system", "user"),
        model=MODEL,
        temperature=0.0,
        base_url=BASE_URL,
        response=None if call.failed else "answer",
        error="RateLimitError: quota" if call.failed else None,
        usage={"total_tokens": call.tokens},
        replayed_from=call.replayed_from,
    )


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
