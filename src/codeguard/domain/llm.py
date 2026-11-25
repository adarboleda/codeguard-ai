"""Data exchanged with a language model when it proposes tests (CG-31, optional)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .errors import CodeGuardError

# First line of the placeholder proposal written when the model gave no usable answer.
# The validator turns it into a GENERATION_ERROR, so failed calls stay in the denominator.
GENERATION_ERROR_MARKER = "# codeguard: generation-error:"


class LlmError(CodeGuardError):
    """The model could not produce an answer (network, quota, timeout, missing key...)."""


@dataclass(frozen=True)
class LlmPrompt:
    """A chat prompt: system instructions plus the black-box description of one function."""

    system: str
    user: str


@dataclass(frozen=True)
class LlmReply:
    """Raw text returned by the model, with the model name and token usage if known."""

    text: str
    model: str
    usage: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))
