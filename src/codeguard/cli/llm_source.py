"""Build the Groq ProposalSource for ``codeguard generate --source groq`` (CG-31).

Live mode reads ``GROQ_API_KEY`` and ``CODEGUARD_LLM_MODEL`` from the environment or
``.env``; replay mode (``--replay <run_id>``) needs neither key nor network.
"""

import os
from enum import StrEnum
from pathlib import Path

from codeguard.adapters.config import load_settings
from codeguard.adapters.llm import (
    LLM_DIR_NAME,
    GroqProposalSource,
    OpenAICompatibleClient,
    ReplayLlmClient,
)
from codeguard.domain.llm import GENERATION_ERROR_MARKER, LlmError
from codeguard.ports.llm import LlmClient

API_KEY_ENV = "GROQ_API_KEY"
MODEL_ENV = "CODEGUARD_LLM_MODEL"


class SourceOption(StrEnum):
    """Where proposals come from."""

    TEMPLATE = "template"
    GROQ = "groq"


def build_groq_source(
    out: Path, run_id: str, reference_dir: Path, replay: str | None
) -> GroqProposalSource:
    """Groq source writing its records to ``out/<run_id>/llm/``."""
    settings = load_settings().llm
    client: LlmClient
    if replay is not None:
        client = ReplayLlmClient(out / _single_name(replay) / LLM_DIR_NAME)
    else:
        _load_dotenv()
        client = OpenAICompatibleClient(
            api_key=os.environ.get(API_KEY_ENV, "").strip(),
            model=os.environ.get(MODEL_ENV, "").strip(),
            base_url=settings.base_url,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
    return GroqProposalSource(
        client,
        out / run_id / LLM_DIR_NAME,
        reference_dir,
        max_tests_per_function=settings.max_tests_per_function,
        temperature=settings.temperature,
        base_url=settings.base_url,
        replayed_from=replay,
    )


def count_generation_errors(codes: list[str]) -> int:
    return sum(1 for code in codes if code.lstrip().startswith(GENERATION_ERROR_MARKER))


def _single_name(run_id: str) -> str:
    cleaned = run_id.strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise LlmError(f"Invalid replay run_id {run_id!r}: must be a single directory name")
    return cleaned


def _load_dotenv() -> None:
    """Load ``./.env`` (current directory only) without overriding existing variables.

    The path is explicit on purpose: ``load_dotenv()`` alone searches upwards from this
    file's folder and could pick up a key the user did not mean to use.
    """
    try:
        from dotenv import load_dotenv  # optional dependency (extra "llm")
    except ImportError:
        return
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
