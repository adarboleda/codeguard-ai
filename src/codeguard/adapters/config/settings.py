"""Read ``codeguard.toml``: timeouts and other tunables live here, not in the code.

Plan, section 4.4: no magic numbers. Unknown keys are rejected so a typo such as
``timeout_secons`` fails loudly instead of being silently ignored.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from codeguard.adapters.execution import DEFAULT_TIMEOUT_SECONDS
from codeguard.domain.errors import CodeGuardError

DEFAULT_CONFIG_FILE = Path("codeguard.toml")


class ConfigError(CodeGuardError):
    """Raised when ``codeguard.toml`` cannot be read or has invalid values."""


@dataclass(frozen=True)
class RunnerSettings:
    """``[runner]`` section."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class Settings:
    """All CodeGuard settings."""

    runner: RunnerSettings = field(default_factory=RunnerSettings)


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
    return Settings(runner=_runner_settings(data.get("runner", {}), path))


def _runner_settings(section: object, path: Path) -> RunnerSettings:
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [runner] must be a table")
    unknown = sorted(set(section) - {"timeout_seconds"})
    if unknown:
        raise ConfigError(f"{path}: unknown keys in [runner]: {', '.join(unknown)}")
    timeout = section.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        raise ConfigError(f"{path}: [runner] timeout_seconds must be a positive number")
    return RunnerSettings(timeout_seconds=float(timeout))
