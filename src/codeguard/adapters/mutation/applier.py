"""Apply catalog mutants to temporary copies of the reference package (CG-14).

Each mutant lives in its own temporary directory. The original ``reference/sciref``
is never written: its per-file SHA-256 digests are compared before and after use.
"""

import hashlib
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import yaml

from codeguard.domain.errors import CodeGuardError

PACKAGE_NAME = "sciref"


class MutantApplyError(CodeGuardError):
    """Raised when a catalog is malformed or a mutant cannot be applied exactly once."""


class MutantSiteError(MutantApplyError):
    """The snippet to mutate is absent or ambiguous: the mutant is invalid, not the package."""


@dataclass(frozen=True)
class MutantSpec:
    """One catalog entry: replace ``original`` by ``mutated`` in the reference package."""

    id: str
    function: str
    original: str
    mutated: str
    equivalent: bool = False


def load_catalog(path: Path) -> tuple[MutantSpec, ...]:
    """Read ``mutants/catalog.yaml`` and return its mutants in file order."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("mutants"), list):
        raise MutantApplyError(f"{path}: expected a top-level 'mutants' list")

    specs: list[MutantSpec] = []
    for entry in raw["mutants"]:
        try:
            specs.append(
                MutantSpec(
                    id=str(entry["id"]),
                    function=str(entry["function"]),
                    original=str(entry["original"]),
                    mutated=str(entry["mutated"]),
                    equivalent=entry.get("status") == "equivalent",
                )
            )
        except (KeyError, TypeError) as exc:
            raise MutantApplyError(f"{path}: malformed mutant entry {entry!r}") from exc

    ids = [spec.id for spec in specs]
    duplicates = sorted({mid for mid in ids if ids.count(mid) > 1})
    if duplicates:
        raise MutantApplyError(f"{path}: duplicate mutant ids {duplicates}")
    return tuple(specs)


def file_digests(package_dir: Path) -> dict[str, str]:
    """SHA-256 of every ``.py`` file under ``package_dir``.

    Keys look like ``sciref/numeric.py``, the format of ``reference/sciref.sha256``.
    """
    digests: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*.py")):
        relative = path.relative_to(package_dir.parent).as_posix()
        digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def apply_mutant(spec: MutantSpec, package_copy: Path) -> Path:
    """Replace ``spec.original`` by ``spec.mutated`` in the copy under ``package_copy``.

    The snippet must occur exactly once in the whole package; otherwise the mutant
    is ambiguous and ``MutantApplyError`` is raised.
    """
    matches: list[tuple[Path, str]] = []
    occurrences = 0
    for path in sorted(package_copy.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        count = text.count(spec.original)
        if count:
            matches.append((path, text))
            occurrences += count

    if occurrences != 1:
        raise MutantSiteError(
            f"{spec.id}: original snippet found {occurrences} times, expected exactly 1"
        )

    target, text = matches[0]
    target.write_text(text.replace(spec.original, spec.mutated, 1), encoding="utf-8")
    return target


@contextmanager
def mutant_workspace(spec: MutantSpec, reference_dir: Path) -> Iterator[Path]:
    """Yield a temporary directory that contains a mutated copy of ``sciref``.

    The yielded path is the parent of ``sciref/``, so it can go on ``sys.path``.
    The temporary directory is removed on exit. If the original package changed
    while the copy was in use, ``MutantApplyError`` is raised after the block.
    """
    source = reference_dir / PACKAGE_NAME
    before = file_digests(source)

    with tempfile.TemporaryDirectory(prefix=f"codeguard-{spec.id}-") as tmp:
        copy_root = Path(tmp) / PACKAGE_NAME
        shutil.copytree(source, copy_root, ignore=shutil.ignore_patterns("__pycache__"))
        apply_mutant(spec, copy_root)
        yield Path(tmp)

    if file_digests(source) != before:
        raise MutantApplyError(f"{spec.id}: original {PACKAGE_NAME} package was modified")
