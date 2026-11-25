"""Tests for the LLM clients, records and GroqProposalSource. No test touches the network."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codeguard.adapters.llm import (
    GroqProposalSource,
    OpenAICompatibleClient,
    ReplayLlmClient,
    read_record,
    write_record,
)
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.domain import ProposalSourceKind
from codeguard.domain.llm import GENERATION_ERROR_MARKER, LlmError, LlmPrompt, LlmReply

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "reference"
CONTRACTS = YamlSpecRepository(REPO_ROOT / "specs" / "contracts.yaml", [REFERENCE_DIR]).load()
PROMPT = LlmPrompt(system="sys", user="usr")
SECRET = "gsk_" + "s3cr3t" * 8


# ---------------------------------------------------------------- OpenAI-compatible client


class _FakeCompletions:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        message = SimpleNamespace(content=self.behaviour)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model="m-1", usage=usage)


def _client(behaviour: Any) -> tuple[OpenAICompatibleClient, _FakeCompletions, dict[str, Any]]:
    completions = _FakeCompletions(behaviour)
    factory_args: dict[str, Any] = {}

    def factory(**kwargs: Any) -> Any:
        factory_args.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    client = OpenAICompatibleClient(
        api_key=SECRET, model="m-1", temperature=0.0, timeout_seconds=60, client_factory=factory
    )
    return client, completions, factory_args


def test_client_sends_one_black_box_request_with_plan_limits() -> None:
    client, completions, factory_args = _client("```python\nx = 1\n```")

    reply = client.complete("sciref.numeric.clamp", PROMPT)

    assert reply == LlmReply(
        "```python\nx = 1\n```",
        "m-1",
        {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )
    assert factory_args == {
        "api_key": SECRET,
        "base_url": "https://api.groq.com/openai/v1",
        "timeout": 60,
        "max_retries": 2,
    }
    (call,) = completions.calls
    assert call["model"] == "m-1"
    assert call["temperature"] == 0.0
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_client_errors_become_llm_errors_without_the_key() -> None:
    client, _, _ = _client(RuntimeError(f"rate limited for key {SECRET}"))

    with pytest.raises(LlmError) as info:
        client.complete("sciref.numeric.clamp", PROMPT)

    assert "RuntimeError: rate limited" in str(info.value)
    assert SECRET not in str(info.value)


def test_empty_answer_is_an_error() -> None:
    client, _, _ = _client("   ")

    with pytest.raises(LlmError, match="empty answer"):
        client.complete("f", PROMPT)


@pytest.mark.parametrize(
    ("key", "model", "message"),
    [("", "m", "GROQ_API_KEY is not set"), ("k", "", "CODEGUARD_LLM_MODEL is not set")],
)
def test_missing_key_or_model(key: str, model: str, message: str) -> None:
    with pytest.raises(LlmError, match=message):
        OpenAICompatibleClient(api_key=key, model=model, client_factory=lambda **_: None)


# ---------------------------------------------------------------- records and replay


def _record(llm_dir: Path, function: str, response: str | None, error: str | None = None) -> None:
    write_record(
        llm_dir,
        function=function,
        prompt=PROMPT,
        model="m-1",
        temperature=0.0,
        base_url="https://api.groq.com/openai/v1",
        response=response,
        error=error,
        usage={"total_tokens": 30},
        replayed_from=None,
    )


def test_record_has_the_audit_fields(tmp_path: Path) -> None:
    _record(tmp_path, "sciref.numeric.clamp", "answer")

    record = read_record(tmp_path, "sciref.numeric.clamp")

    assert record["status"] == "ok"
    assert record["model"] == "m-1"
    assert record["temperature"] == 0.0
    assert record["prompt"] == {"system": "sys", "user": "usr"}
    assert record["response"] == "answer"
    assert "requested_at_utc" in record
    assert (tmp_path / "sciref.numeric.clamp.json").is_file()


def test_replay_returns_recorded_answers_and_failures(tmp_path: Path) -> None:
    _record(tmp_path, "ok.fn", "answer")
    _record(tmp_path, "bad.fn", None, error="RateLimitError: quota")
    replay = ReplayLlmClient(tmp_path)

    assert replay.complete("ok.fn", PROMPT) == LlmReply("answer", "m-1", {"total_tokens": 30})
    with pytest.raises(LlmError, match="recorded failure: RateLimitError: quota"):
        replay.complete("bad.fn", PROMPT)
    with pytest.raises(LlmError, match=r"no recorded LLM answer for missing\.fn"):
        replay.complete("missing.fn", PROMPT)


def test_replay_needs_a_records_directory(tmp_path: Path) -> None:
    with pytest.raises(LlmError, match="no recorded LLM answers"):
        ReplayLlmClient(tmp_path / "missing")


def test_unreadable_record(tmp_path: Path) -> None:
    (tmp_path / "f.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "g.json").write_text("[1]", encoding="utf-8")

    with pytest.raises(LlmError, match="unreadable"):
        read_record(tmp_path, "f")
    with pytest.raises(LlmError, match="must be a JSON object"):
        read_record(tmp_path, "g")


# ---------------------------------------------------------------- GroqProposalSource


class _ScriptedClient:
    """Answers with two tests per function, except the ones listed in ``failing``."""

    def __init__(self, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing
        self.calls: list[str] = []

    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, function: str, prompt: LlmPrompt) -> LlmReply:
        self.calls.append(function)
        if function in self.failing:
            raise LlmError(f"{function}: APITimeoutError: timed out")
        module, _, name = function.rpartition(".")
        code = (
            f"from {module} import {name}\n\n"
            f"def test_one():\n    assert {name} is not None\n\n"
            f"def test_two():\n    assert {name} is not None\n"
        )
        return LlmReply(f"```python\n{code}```", "scripted", {"total_tokens": 7})


def test_one_call_per_function_and_one_proposal_per_test(tmp_path: Path) -> None:
    client = _ScriptedClient()

    proposals = GroqProposalSource(client, tmp_path / "llm", REFERENCE_DIR).generate(CONTRACTS)

    assert client.calls == [contract.qualified_name for contract in CONTRACTS]
    assert len(proposals) == 2 * len(CONTRACTS)
    first = proposals[0]
    assert (first.proposal_id, first.file_name) == (
        "groq-weighted_mean-01",
        "test_groq_weighted_mean_01.py",
    )
    assert {p.source for p in proposals} == {ProposalSourceKind.GROQ}
    assert sorted(path.name for path in (tmp_path / "llm").iterdir()) == sorted(
        f"{c.qualified_name}.json" for c in CONTRACTS
    )


def test_failed_call_is_recorded_and_becomes_a_placeholder(tmp_path: Path) -> None:
    failing = frozenset({"sciref.numeric.clamp"})

    proposals = GroqProposalSource(_ScriptedClient(failing), tmp_path, REFERENCE_DIR).generate(
        CONTRACTS
    )

    errors = [p for p in proposals if p.code.startswith(GENERATION_ERROR_MARKER)]
    assert [p.proposal_id for p in errors] == ["groq-clamp-error"]
    assert "APITimeoutError" in errors[0].code
    record = json.loads((tmp_path / "sciref.numeric.clamp.json").read_text(encoding="utf-8"))
    assert (record["status"], record["response"]) == ("error", None)


def test_replay_reproduces_the_same_proposals_without_network(tmp_path: Path) -> None:
    live = GroqProposalSource(_ScriptedClient(), tmp_path / "run1" / "llm", REFERENCE_DIR)
    original = live.generate(CONTRACTS)

    replayed = GroqProposalSource(
        ReplayLlmClient(tmp_path / "run1" / "llm"),
        tmp_path / "run2" / "llm",
        REFERENCE_DIR,
        replayed_from="run1",
    ).generate(CONTRACTS)

    assert [(p.proposal_id, p.code) for p in replayed] == [
        (p.proposal_id, p.code) for p in original
    ]
    record = read_record(tmp_path / "run2" / "llm", "sciref.numeric.clamp")
    assert record["replayed_from"] == "run1"
    assert record["model"] == "scripted"


def test_invalid_maximum() -> None:
    with pytest.raises(ValueError, match="max_tests_per_function"):
        GroqProposalSource(_ScriptedClient(), Path("x"), REFERENCE_DIR, max_tests_per_function=0)
