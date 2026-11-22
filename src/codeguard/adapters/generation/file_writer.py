"""Filesystem ProposalWriter adapter that writes ``test_*.py`` files and manifest (CG-07)."""

import json
import re
from collections.abc import Sequence
from pathlib import Path

from codeguard.domain import TestProposal

MANIFEST_FILE_NAME = "manifest.json"
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z_]\w*\.py$", re.ASCII)


class FileProposalWriter:
    """Persists generated ``TestProposal`` modules into ``out/<run_id>/proposals/``."""

    def write(self, proposals: Sequence[TestProposal], proposals_dir: Path) -> tuple[Path, ...]:
        """Validate file names, create ``proposals_dir``, and write files plus manifest."""
        seen_names: set[str] = set()
        for proposal in proposals:
            _validate_file_name(proposal.file_name)
            if proposal.file_name in seen_names:
                raise ValueError(f"duplicate proposal file_name: {proposal.file_name}")
            seen_names.add(proposal.file_name)

        proposals_dir.mkdir(parents=True, exist_ok=True)
        written_paths: list[Path] = []
        for proposal in proposals:
            target_path = proposals_dir / proposal.file_name
            target_path.write_text(proposal.code, encoding="utf-8")
            written_paths.append(target_path)

        _write_manifest(proposals, proposals_dir)
        return tuple(written_paths)


def _write_manifest(proposals: Sequence[TestProposal], proposals_dir: Path) -> None:
    records = [
        {
            "proposal_id": proposal.proposal_id,
            "target_module": proposal.target_module,
            "target_function": proposal.target_function,
            "source": proposal.source.value,
            "case_ids": list(proposal.case_ids),
            "file_name": proposal.file_name,
        }
        for proposal in proposals
    ]
    manifest_path = proposals_dir / MANIFEST_FILE_NAME
    manifest_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _validate_file_name(file_name: str) -> None:
    if not _SAFE_FILE_NAME.match(file_name):
        raise ValueError(f"unsafe proposal file_name: {file_name!r}")
