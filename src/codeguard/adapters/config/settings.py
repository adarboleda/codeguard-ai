"""Read ``codeguard.toml``: timeouts and other tunables live here, not in the code.

Plan, section 4.4: no magic numbers. Unknown keys are rejected so a typo such as
``timeout_secons`` fails loudly instead of being silently ignored.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from codeguard.adapters.execution import DEFAULT_TIMEOUT_SECONDS
from codeguard.adapters.llm import DEFAULT_MAX_TESTS_PER_FUNCTION, GROQ_BASE_URL
from codeguard.adapters.validation.import_rule import (
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_IMPORT_TIMEOUT_SECONDS,
)
from codeguard.domain.coverage import CoverageTargets
from codeguard.domain.errors import CodeGuardError

DEFAULT_CONFIG_FILE = Path("codeguard.toml")
# Team targets from the plan (section 1), above the guide's 70 % / 70 % minimum.
DEFAULT_MIN_LINE_PCT = 90.0
DEFAULT_MIN_BRANCH_PCT = 85.0
_MAX_PCT = 100.0


class ConfigError(CodeGuardError):
    """Raised when ``codeguard.toml`` cannot be read or has invalid values."""


@dataclass(frozen=True)
class RunnerSettings:
    """``[runner]`` section."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    import_timeout_seconds: float = DEFAULT_IMPORT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class LlmSettings:
    """``[llm]`` section: limits of the optional Groq extension (plan, section 2.4).

    The API key and the model id are not here: they come from ``.env``
    (``GROQ_API_KEY``, ``CODEGUARD_LLM_MODEL``) so they never reach the repository.
    """

    base_url: str = GROQ_BASE_URL
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_tests_per_function: int = DEFAULT_MAX_TESTS_PER_FUNCTION


@dataclass(frozen=True)
class Settings:
    """All CodeGuard settings."""

    runner: RunnerSettings = field(default_factory=RunnerSettings)
    coverage: CoverageTargets = field(
        default_factory=lambda: CoverageTargets(DEFAULT_MIN_LINE_PCT, DEFAULT_MIN_BRANCH_PCT)
    )
    llm: LlmSettings = field(default_factory=LlmSettings)


def load_settings(path: Path = DEFAULT_CONFIG_FILE, *, required: bool = False) -> Settings:
    """Load settings; a missing file gives the defaults unless ``required`` is True."""
    if not path.is_file():
        if required:
            raise ConfigError(f"configuration file not found: {path}")
        return Settings()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    return Settings(
        runner=_runner_settings(data.get("runner", {}), path),
        coverage=_coverage_targets(data.get("coverage", {}), path),
        llm=_llm_settings(data.get("llm", {}), path),
    )


def _runner_settings(section: object, path: Path) -> RunnerSettings:
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [runner] must be a table")
    unknown = sorted(set(section) - {"timeout_seconds", "import_timeout_seconds"})
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [runner]: {', '.join(unknown)}")
    timeout = _positive_float(section, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS, path)
    import_timeout = _positive_float(
        section, "import_timeout_seconds", DEFAULT_IMPORT_TIMEOUT_SECONDS, path
    )
    return RunnerSettings(timeout_seconds=timeout, import_timeout_seconds=import_timeout)


def _coverage_targets(section: object, path: Path) -> CoverageTargets:
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [coverage] must be a table")
    unknown = sorted(set(section) - {"min_line_pct", "min_branch_pct"})
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [coverage]: {', '.join(unknown)}")
    return CoverageTargets(
        min_line_pct=_percentage(section, "min_line_pct", DEFAULT_MIN_LINE_PCT, path),
        min_branch_pct=_percentage(section, "min_branch_pct", DEFAULT_MIN_BRANCH_PCT, path),
    )


def _percentage(section: dict[object, object], key: str, default: float, path: Path) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= _MAX_PCT:
        raise ConfigError(f"{path}: [coverage] {key} must be a number between 0 and 100")
    return float(value)


def _positive_float(section: dict[object, object], key: str, default: float, path: Path) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ConfigError(f"{path}: [runner] {key} must be a positive number")
    return float(value)


_LLM_KEYS = {"base_url", "temperature", "timeout_seconds", "max_retries", "max_tests_per_function"}


def _llm_settings(section: object, path: Path) -> LlmSettings:
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [llm] must be a table")
    unknown = sorted(set(section) - _LLM_KEYS)
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [llm]: {', '.join(unknown)}")
    defaults = LlmSettings()
    base_url = section.get("base_url", defaults.base_url)
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        raise ConfigError(f"{path}: [llm] base_url must be an https:// URL")
    return LlmSettings(
        base_url=base_url,
        temperature=_llm_number(section, "temperature", defaults.temperature, 0.0, 2.0, path),
        timeout_seconds=_llm_number(
            section, "timeout_seconds", defaults.timeout_seconds, 1, 600, path
        ),
        max_retries=int(
            _llm_number(section, "max_retries", defaults.max_retries, 0, 5, path, integer=True)
        ),
        max_tests_per_function=int(
            _llm_number(
                section,
                "max_tests_per_function",
                defaults.max_tests_per_function,
                1,
                20,
                path,
                integer=True,
            )
        ),
    )


def _llm_number(
    section: dict[object, object],
    key: str,
    default: float,
    low: float,
    high: float,
    path: Path,
    *,
    integer: bool = False,
) -> float:
    value = section.get(key, default)
    allowed = int if integer else int | float
    if isinstance(value, bool) or not isinstance(value, allowed) or not low <= value <= high:
        kind = "an integer" if integer else "a number"
        raise ConfigError(f"{path}: [llm] {key} must be {kind} between {low:g} and {high:g}")
    return float(value)
