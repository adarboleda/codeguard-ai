"""Tests for codeguard.toml loading."""

from pathlib import Path

import pytest

from codeguard.adapters.config import ConfigError, RunnerSettings, Settings, load_settings

REPO_CONFIG = Path(__file__).resolve().parents[2] / "codeguard.toml"


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "codeguard.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_config_is_valid() -> None:
    assert load_settings(REPO_CONFIG, required=True) == Settings(RunnerSettings(60.0))


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "codeguard.toml") == Settings()


def test_missing_file_is_an_error_when_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "codeguard.toml", required=True)


@pytest.mark.parametrize(("value", "expected"), [("5", 5.0), ("2.5", 2.5)])
def test_timeout_is_read(tmp_path: Path, value: str, expected: float) -> None:
    path = _config(tmp_path, f"[runner]\ntimeout_seconds = {value}\n")

    assert load_settings(path).runner.timeout_seconds == expected


@pytest.mark.parametrize(("value", "expected"), [("5", 5.0), ("1.5", 1.5)])
def test_import_timeout_is_read(tmp_path: Path, value: str, expected: float) -> None:
    path = _config(tmp_path, f"[runner]\nimport_timeout_seconds = {value}\n")

    assert load_settings(path).runner.import_timeout_seconds == expected


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(_config(tmp_path, "")) == Settings()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[runner]\ntimeout_seconds = 0\n", "positive number"),
        ("[runner]\ntimeout_seconds = -1\n", "positive number"),
        ("[runner]\ntimeout_seconds = true\n", "positive number"),
        ('[runner]\ntimeout_seconds = "60"\n', "positive number"),
        ("[runner]\nimport_timeout_seconds = 0\n", "positive number"),
        ("[runner]\nimport_timeout_seconds = -1\n", "positive number"),
        ("[runner]\nimport_timeout_seconds = true\n", "positive number"),
        ('[runner]\nimport_timeout_seconds = "10"\n', "positive number"),
        ("[runner]\ntimeout_secons = 60\n", "unknown keys in \\[runner\\]: timeout_secons"),
        ("runner = 5\n", "must be a table"),
        ("[runner\n", "cannot read"),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(_config(tmp_path, text))


def test_coverage_targets_default_to_the_team_goals(tmp_path: Path) -> None:
    targets = load_settings(tmp_path / "missing.toml").coverage

    assert (targets.min_line_pct, targets.min_branch_pct) == (90.0, 85.0)


def test_repository_coverage_targets() -> None:
    targets = load_settings(REPO_CONFIG, required=True).coverage

    assert (targets.min_line_pct, targets.min_branch_pct) == (90.0, 85.0)


def test_coverage_targets_are_read(tmp_path: Path) -> None:
    path = _config(tmp_path, "[coverage]\nmin_line_pct = 70\nmin_branch_pct = 70.5\n")

    targets = load_settings(path).coverage

    assert (targets.min_line_pct, targets.min_branch_pct) == (70.0, 70.5)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[coverage]\nmin_line_pct = 101\n", "between 0 and 100"),
        ("[coverage]\nmin_branch_pct = -5\n", "between 0 and 100"),
        ("[coverage]\nmin_line_pct = true\n", "between 0 and 100"),
        ('[coverage]\nmin_line_pct = "90"\n', "between 0 and 100"),
        ("[coverage]\nmin_lines = 90\n", r"unknown keys in \[coverage\]: min_lines"),
        ("coverage = 90\n", r"\[coverage\] must be a table"),
    ],
)
def test_invalid_coverage_targets_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(_config(tmp_path, text))


def test_llm_settings_defaults_follow_the_plan(tmp_path: Path) -> None:
    llm = load_settings(tmp_path / "missing.toml").llm

    assert llm.base_url == "https://api.groq.com/openai/v1"
    assert (llm.temperature, llm.timeout_seconds, llm.max_retries) == (0.0, 60.0, 2)
    assert llm.max_tests_per_function == 8


def test_repository_llm_settings() -> None:
    assert load_settings(REPO_CONFIG, required=True).llm == load_settings(Path("missing")).llm


def test_llm_settings_are_read(tmp_path: Path) -> None:
    text = (
        "[llm]\ntemperature = 0.2\ntimeout_seconds = 30\n"
        "max_retries = 0\nmax_tests_per_function = 3\n"
    )

    llm = load_settings(_config(tmp_path, text)).llm

    assert (llm.temperature, llm.timeout_seconds, llm.max_retries) == (0.2, 30.0, 0)
    assert llm.max_tests_per_function == 3


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[llm]\nbase_url = "http://insecure"\n', "https:// URL"),
        ("[llm]\ntemperature = 3\n", "temperature must be a number"),
        ("[llm]\nmax_retries = 1.5\n", "max_retries must be an integer"),
        ("[llm]\nmax_tests_per_function = 0\n", "max_tests_per_function must be an integer"),
        ("[llm]\ntimeout_seconds = true\n", "timeout_seconds must be a number"),
        ('[llm]\napi_key = "gsk_x"\n', r"unknown keys in \[llm\]: api_key"),
        ("llm = 1\n", r"\[llm\] must be a table"),
    ],
)
def test_invalid_llm_settings_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(_config(tmp_path, text))
