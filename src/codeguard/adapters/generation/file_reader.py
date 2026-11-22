"""Filesystem ProposalReader adapter reading ``manifest.json`` and ``test_*.py`` files."""

import json
import re
from collections.abc import Mapping
from pathlib import Path

from codeguard.adapters.generation.file_writer import MANIFEST_FILE_NAME
from codeguard.domain import ProposalSourceKind, TestProposal

_SAFE_FILE_NAME = re.compile(r"^[A-Za-z_]\w*\.py$", re.ASCII)


class FileProposalReader:
    """Loads persisted ``TestProposal`` objects from ``out/<run_id>/proposals/``."""

    def read(self, proposals_dir: Path) -> tuple[TestProposal, ...]:
        """Read ``manifest.json`` and load each referenced proposal source file."""
        manifest_path = proposals_dir / MANIFEST_FILE_NAME
        records = _load_manifest_records(manifest_path)
        return tuple(_build_proposal(record, proposals_dir) for record in records)


def _load_manifest_records(manifest_path: Path) -> list[dict[str, object]]:
    if not manifest_path.is_file():
        raise ValueError(
            f"Proposals manifest not found: {manifest_path}; run 'codeguard generate' first"
        )
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid proposals manifest '{manifest_path}': {error}") from error
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError(f"Proposals manifest '{manifest_path}' must be a JSON array of objects")
    return raw


def _build_proposal(record: Mapping[str, object], proposals_dir: Path) -> TestProposal:
    file_name = _require_str(record, "file_name")
    if not _SAFE_FILE_NAME.match(file_name):
        raise ValueError(f"unsafe proposal file_name in manifest: {file_name!r}")
    source_path = proposals_dir / file_name
    if not source_path.is_file():
        raise ValueError(f"Proposal source file not found: {source_path}")
    try:
        code = source_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"Failed to read proposal file '{source_path}': {error}") from error
    return TestProposal(
        proposal_id=_require_str(record, "proposal_id"),
        target_module=_require_str(record, "target_module"),
        target_function=_require_str(record, "target_function"),
        source=ProposalSourceKind(_require_str(record, "source")),
        code=code,
        case_ids=_require_case_ids(record),
        file_name=file_name,
    )


def _require_str(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {key!r} must be a non-empty string")
    return value


def _require_case_ids(record: Mapping[str, object]) -> tuple[str, ...]:
    value = record.get("case_ids")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("manifest field 'case_ids' must be a list of strings")
    return tuple(value)
