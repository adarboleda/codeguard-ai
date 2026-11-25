"""Raw LLM answers stored in ``out/<run_id>/llm/<module.function>.json`` (CG-31).

Every call is recorded (answer or error) with model, temperature, prompt and date,
so a run can be audited and replayed later without network or API key.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from codeguard.domain.llm import LlmError, LlmPrompt

LLM_DIR_NAME = "llm"


def record_path(llm_dir: Path, function: str) -> Path:
    return llm_dir / f"{function}.json"


def write_record(
    llm_dir: Path,
    *,
    function: str,
    prompt: LlmPrompt,
    model: str,
    temperature: float,
    base_url: str,
    response: str | None,
    error: str | None,
    usage: Mapping[str, int],
    replayed_from: str | None,
) -> Path:
    """Write one exchange; never contains the API key (it is not passed here)."""
    llm_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "function": function,
        "provider": "groq",
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "requested_at_utc": datetime.now(UTC).isoformat(),
        "status": "error" if error is not None else "ok",
        "prompt": {"system": prompt.system, "user": prompt.user},
        "response": response,
        "error": error,
        "usage": dict(usage),
        "replayed_from": replayed_from,
    }
    path = record_path(llm_dir, function)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_record(llm_dir: Path, function: str) -> dict[str, object]:
    """Load one recorded exchange; ``LlmError`` if it is missing or unreadable."""
    path = record_path(llm_dir, function)
    if not path.is_file():
        raise LlmError(f"no recorded LLM answer for {function} in {llm_dir}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LlmError(f"unreadable LLM record {path}: {error}") from error
    if not isinstance(record, dict):
        raise LlmError(f"LLM record {path} must be a JSON object")
    return record
