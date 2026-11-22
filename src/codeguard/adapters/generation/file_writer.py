"""Filesystem ProposalWriter adapter that writes ``test_*.py`` files (CG-07)."""

import re
from collections.abc import Sequence
from pathlib import Path

from codeguard.domain import TestProposal

_SAFE_FILE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.py$")


class FileProposalWriter:
    """Persists generated ``TestProposal`` modules into ``out/<run_id>/proposals/``."""

    def write(self, proposals: Sequence[TestProposal], proposals_dir: Path) -> tuple[Path, ...]:
        """Validate file names, create ``proposals_dir``, and write each proposal."""
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
        return tuple(written_paths)


def _validate_file_name(file_name: str) -> None:
    if not _SAFE_FILE_NAME.match(file_name):
        raise ValueError(f"unsafe proposal file_name: {file_name!r}")
