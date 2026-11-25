"""Optional LLM extension (CG-31): Groq proposals, recorded and replayable."""

from .clients import GROQ_BASE_URL, OpenAICompatibleClient, ReplayLlmClient
from .groq_source import DEFAULT_MAX_TESTS_PER_FUNCTION, GroqProposalSource
from .prompt import build_prompt, read_docstring
from .records import LLM_DIR_NAME, read_record, record_path, write_record
from .response import extract_code, split_tests

__all__ = [
    "DEFAULT_MAX_TESTS_PER_FUNCTION",
    "GROQ_BASE_URL",
    "LLM_DIR_NAME",
    "GroqProposalSource",
    "OpenAICompatibleClient",
    "ReplayLlmClient",
    "build_prompt",
    "extract_code",
    "read_docstring",
    "read_record",
    "record_path",
    "split_tests",
    "write_record",
]
