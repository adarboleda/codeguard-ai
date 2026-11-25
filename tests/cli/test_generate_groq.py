"""Acceptance test of CG-31: ``generate --source groq --replay <run_id>`` works without a key.

The recorded answers are written by the test itself, so nothing here touches the network.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from codeguard.adapters.llm import write_record
from codeguard.cli.main import app
from codeguard.domain.llm import LlmPrompt

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"

runner = CliRunner()

ANSWERS: dict[str, str | None] = {
    "sciref.numeric.weighted_mean": (
        "def test_basic():\n    assert weighted_mean([1, 3], [1, 3]) == pytest.approx(2.5)\n\n"
        "def test_empty():\n    with pytest.raises(ValueError):\n        weighted_mean([], [])\n\n"
        "def test_wrong():\n    assert weighted_mean([1, 2, 3], [1, 1, 1]) == 3.0\n"
    ),
    "sciref.numeric.clamp": None,  # the call failed (e.g. quota)
    "sciref.numeric.normalize_minmax": (
        "def test_n():\n    assert normalize_minmax([2, 4]) == [0.0, 1.0]\n"
    ),
    "sciref.signals.moving_average": (
        "def test_m():\n    assert moving_average([1, 2, 3], 2) == [1.5, 2.5]\n"
    ),
    "sciref.signals.threshold_crossings": (
        "def test_t():\n    assert threshold_crossings([0, 5], 5) == [1]\n"
    ),
    "sciref.validation.validate_range": (
        "def test_v():\n    assert validate_range(5, 0, 10) is True\n"
    ),
}


def _record_answers(llm_dir: Path) -> None:
    for function, body in ANSWERS.items():
        module, _, name = function.rpartition(".")
        response = (
            None
            if body is None
            else f"```python\nimport pytest\nfrom {module} import {name}\n\n{body}```"
        )
        write_record(
            llm_dir,
            function=function,
            prompt=LlmPrompt("sys", "usr"),
            model="openai/gpt-oss-120b",
            temperature=0.0,
            base_url="https://api.groq.com/openai/v1",
            response=response,
            error="RateLimitError: quota exceeded" if body is None else None,
            usage={},
            replayed_from=None,
        )


def _invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


@pytest.fixture
def no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No key, no model, and a working directory without .env."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CODEGUARD_LLM_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _common(out: Path) -> list[str]:
    return [
        "--specs",
        str(CONTRACTS_PATH),
        "--reference-dir",
        str(REFERENCE_DIR),
        "--out",
        str(out),
    ]


def test_replay_works_without_key_and_keeps_failures_in_the_denominator(no_key: Path) -> None:
    out = no_key / "out"
    _record_answers(out / "recorded" / "llm")

    generated = _invoke(
        "generate", *_common(out), "--source", "groq", "--replay", "recorded", "--run-id", "g1"
    )
    validated = _invoke("validate", *_common(out), "--run-id", "g1")
    executed = _invoke(
        "run", "--run-id", "g1", "--out", str(out), "--reference-dir", str(REFERENCE_DIR)
    )

    assert generated.exit_code == 0, generated.output
    assert "Propuestas generadas: 8 archivos" in generated.output
    assert "Fuente groq (replay de recorded)" in generated.output
    assert "llamadas fallidas: 1" in generated.output
    assert validated.exit_code == 0, validated.output
    assert "6/8 válidas (75.0%), 2 rechazadas" in validated.output
    assert "GENERATION_ERROR=1" in validated.output
    assert "WRONG_EXPECTATION=1" in validated.output
    assert executed.exit_code == 0, executed.output
    assert "6 pruebas | 6 aprobadas" in executed.output
    replayed = (out / "g1" / "llm" / "sciref.numeric.weighted_mean.json").read_text(
        encoding="utf-8"
    )
    assert '"replayed_from": "recorded"' in replayed


def test_live_mode_without_key_fails_with_a_clear_message(no_key: Path) -> None:
    result = _invoke("generate", *_common(no_key / "out"), "--source", "groq", "--run-id", "live")

    assert result.exit_code == 1
    assert "GROQ_API_KEY is not set: add it to .env, or use --replay <run_id>" in result.output


def test_replay_only_applies_to_groq(no_key: Path) -> None:
    result = _invoke("generate", *_common(no_key / "out"), "--replay", "x", "--run-id", "t")

    assert result.exit_code == 1
    assert "--replay only applies to --source groq" in result.output


@pytest.mark.parametrize(
    ("replay", "message"), [("missing", "no recorded LLM answers"), ("../x", "Invalid replay")]
)
def test_bad_replay_run_is_an_error(no_key: Path, replay: str, message: str) -> None:
    result = _invoke(
        "generate",
        *_common(no_key / "out"),
        "--source",
        "groq",
        "--replay",
        replay,
        "--run-id",
        "t",
    )

    assert result.exit_code == 1
    assert message in result.output


def test_templates_stay_the_default(no_key: Path) -> None:
    result = _invoke("generate", *_common(no_key / "out"), "--run-id", "tpl", "--no-seeds")

    assert result.exit_code == 0, result.output
    assert "46 archivos" in result.output
    assert "Fuente groq" not in result.output
    assert not (no_key / "out" / "tpl" / "llm").exists()
