"""SHA-256 integrity verification for ``reference/sciref`` before and after execution."""

import hashlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from codeguard.domain.errors import IntegrityError

SCIREF_PACKAGE_NAME = "sciref"
SCIREF_DIGEST_FILE_NAME = "sciref.sha256"


@dataclass(frozen=True)
class ScirefSnapshot:
    """Immutable SHA-256 snapshot of all files under ``reference/sciref``."""

    combined_sha256: str
    files: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation matching ``run_config.json``."""
        return {"combined": self.combined_sha256, "files": dict(self.files)}


def compute_sciref_snapshot(reference_dir: Path) -> ScirefSnapshot:
    """Compute per-file and combined SHA-256 hashes for ``reference_dir / 'sciref'``."""
    package_dir = reference_dir / SCIREF_PACKAGE_NAME
    if not package_dir.is_dir():
        raise IntegrityError(f"reference package not found: {package_dir}")

    files: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(reference_dir).as_posix()
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest_lines = "".join(
        f"{digest}  {rel_path}\n" for rel_path, digest in sorted(files.items())
    )
    combined = hashlib.sha256(manifest_lines.encode("utf-8")).hexdigest()
    return ScirefSnapshot(combined_sha256=combined, files=MappingProxyType(files))


def load_expected_digests(digest_file: Path) -> dict[str, str]:
    """Parse ``sciref.sha256`` into a ``{relative_path: sha256}`` mapping."""
    expected: dict[str, str] = {}
    for line_no, raw_line in enumerate(
        digest_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise IntegrityError(f"malformed digest line {line_no} in {digest_file}: {raw_line!r}")
        digest, relative = parts
        expected[relative.strip()] = digest.strip().lower()
    return expected


def verify_against_manifest(reference_dir: Path, snapshot: ScirefSnapshot) -> None:
    """Verify ``snapshot`` matches ``reference_dir / 'sciref.sha256'`` when present."""
    digest_file = reference_dir / SCIREF_DIGEST_FILE_NAME
    if not digest_file.is_file():
        return
    expected = load_expected_digests(digest_file)
    actual = dict(snapshot.files)
    if actual != expected:
        diff = _diff_files(expected, actual)
        raise IntegrityError(
            f"sciref integrity check failed before run against {digest_file} ({diff}); aborting"
        )


@contextmanager
def verify_sciref_integrity(
    reference_dir: Path,
    *,
    check_manifest: bool = True,
) -> Iterator[ScirefSnapshot]:
    """Verify ``sciref`` SHA-256 hashes before and after executing a protected block."""
    before = compute_sciref_snapshot(reference_dir)
    if check_manifest:
        verify_against_manifest(reference_dir, before)

    try:
        yield before
    finally:
        after = compute_sciref_snapshot(reference_dir)
        if after.files != before.files or after.combined_sha256 != before.combined_sha256:
            diff = _diff_files(before.files, after.files)
            raise IntegrityError(
                f"sciref integrity check failed after run: hash changed ({diff}); aborting"
            )


def _diff_files(before: Mapping[str, str], after: Mapping[str, str]) -> str:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(path for path in (set(before) & set(after)) if before[path] != after[path])

    parts: list[str] = []
    if modified:
        parts.append(f"modified: {', '.join(modified)}")
    if added:
        parts.append(f"added: {', '.join(added)}")
    if removed:
        parts.append(f"removed: {', '.join(removed)}")
    return "; ".join(parts) if parts else "digest mismatch"
