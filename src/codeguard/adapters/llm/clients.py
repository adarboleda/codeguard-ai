"""LLM clients: Groq through the OpenAI-compatible API, or replay of recorded answers."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from codeguard.adapters.llm.records import read_record
from codeguard.domain.llm import LlmError, LlmPrompt, LlmReply

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")

ClientFactory = Callable[..., Any]


class OpenAICompatibleClient:
    """Live client (``openai`` SDK with Groq's ``base_url``). One request per call.

    ``client_factory`` exists for tests: they inject a double, so no test touches the network.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = GROQ_BASE_URL,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not api_key:
            raise LlmError("GROQ_API_KEY is not set: add it to .env, or use --replay <run_id>")
        if not model:
            raise LlmError("CODEGUARD_LLM_MODEL is not set: add the Groq model id to .env")
        factory = client_factory or _openai_factory
        self._client = factory(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=max_retries
        )
        self._api_key = api_key
        self._model = model
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    def complete(self, function: str, prompt: LlmPrompt) -> LlmReply:
        """Ask once (the SDK retries transient errors); ``LlmError`` on any failure."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
            )
            text = response.choices[0].message.content or ""
        except Exception as error:  # SDK errors: network, quota, timeout, auth, bad payload
            message = f"{type(error).__name__}: {error}".replace(self._api_key, "***")
            raise LlmError(f"{function}: {message}") from error
        if not text.strip():
            raise LlmError(f"{function}: the model returned an empty answer")
        return LlmReply(text=text, model=str(response.model or self._model), usage=_usage(response))


class ReplayLlmClient:
    """Answers from ``out/<run_id>/llm/`` records: same tests, no network, no key."""

    def __init__(self, records_dir: Path) -> None:
        if not records_dir.is_dir():
            raise LlmError(f"no recorded LLM answers in {records_dir}")
        self._records_dir = records_dir

    @property
    def model(self) -> str:
        return "replay"

    def complete(self, function: str, prompt: LlmPrompt) -> LlmReply:
        """Return the recorded answer; a recorded failure is replayed as the same failure."""
        record = read_record(self._records_dir, function)
        response = record.get("response")
        if not isinstance(response, str):
            raise LlmError(f"{function}: recorded failure: {record.get('error')}")
        usage = record.get("usage")
        return LlmReply(
            text=response,
            model=str(record.get("model") or "replay"),
            usage=usage if isinstance(usage, Mapping) else {},
        )


def _usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    values = {name: getattr(usage, name, None) for name in _USAGE_FIELDS}
    return {name: value for name, value in values.items() if isinstance(value, int)}


def _openai_factory(**kwargs: Any) -> Any:
    try:
        from openai import OpenAI  # optional dependency: only the Groq extension needs it
    except ImportError as error:
        raise LlmError("the 'openai' package is missing: run 'uv sync --extra llm'") from error
    return OpenAI(**kwargs)
