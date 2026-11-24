"""Read ``codeguard.toml``: timeouts and other tunables live here, not in the code.

Plan, section 4.4: no magic numbers. Unknown keys are rejected so a typo such as
``timeout_secons`` fails loudly instead of being silently ignored.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from codeguard.adapters.execution import DEFAULT_TIMEOUT_SECONDS
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
class Settings:
    """All CodeGuard settings."""

    runner: RunnerSettings = field(default_factory=RunnerSettings)
    coverage: CoverageTargets = field(
        default_factory=lambda: CoverageTargets(DEFAULT_MIN_LINE_PCT, DEFAULT_MIN_BRANCH_PCT)
    )


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
