"""Port for a language model client (live API or recorded replay)."""

from typing import Protocol

from codeguard.domain.llm import LlmPrompt, LlmReply


class LlmClient(Protocol):
    """Answers one prompt; raises ``LlmError`` when no answer can be obtained."""

    @property
    def model(self) -> str:
        """Model identifier used for the answers (recorded with every response)."""
        ...

    def complete(self, function: str, prompt: LlmPrompt) -> LlmReply:
        """Return the model's answer for ``function`` (``module.name``)."""
        ...
