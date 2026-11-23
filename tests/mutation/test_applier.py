"""Tests for the mutant catalog loader and temporary-copy applier (CG-14)."""

import ast
from pathlib import Path

import pytest

from codeguard.adapters.mutation import (
    MutantApplyError,
    MutantSpec,
    apply_mutant,
    file_digests,
    load_catalog,
    mutant_workspace,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "mutants" / "catalog.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"
DIGEST_FILE = REFERENCE_DIR / "sciref.sha256"


def _spec(mutant_id: str = "T01", original: str = "x", mutated: str = "y") -> MutantSpec:
    return MutantSpec(id=mutant_id, function="f", original=original, mutated=mutated)


def test_real_catalog_loads_thirteen_mutants() -> None:
    mutants = load_catalog(CATALOG_PATH)

    assert [m.id for m in mutants] == [f"M{i:02d}" for i in range(1, 14)]


def test_reference_digests_match_published_file() -> None:
    expected: dict[str, str] = {}
    for line in DIGEST_FILE.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split(maxsplit=1)
        expected[relative.strip()] = digest

    assert file_digests(REFERENCE_DIR / "sciref") == expected


@pytest.mark.parametrize("mutant", load_catalog(CATALOG_PATH), ids=lambda m: m.id)
def test_every_catalog_mutant_applies_to_exactly_one_site_and_compiles(
    mutant: MutantSpec,
) -> None:
    with mutant_workspace(mutant, REFERENCE_DIR) as root:
        changed: list[Path] = []
        for copy_file in sorted((root / "sciref").rglob("*.py")):
            original_file = REFERENCE_DIR / "sciref" / copy_file.name
            if copy_file.read_text(encoding="utf-8") != original_file.read_text(encoding="utf-8"):
                changed.append(copy_file)

        assert len(changed) == 1
        mutated_text = changed[0].read_text(encoding="utf-8")
        assert mutant.mutated in mutated_text
        ast.parse(mutated_text)


def test_mutant_workspace_leaves_reference_untouched_and_cleans_up() -> None:
    mutant = load_catalog(CATALOG_PATH)[0]
    before = file_digests(REFERENCE_DIR / "sciref")

    with mutant_workspace(mutant, REFERENCE_DIR) as root:
        copy_dir = root
        assert copy_dir.exists()
        assert file_digests(root / "sciref") != before

    assert file_digests(REFERENCE_DIR / "sciref") == before
    assert not copy_dir.exists()


def test_each_mutant_gets_its_own_directory() -> None:
    mutants = load_catalog(CATALOG_PATH)[:2]

    with (
        mutant_workspace(mutants[0], REFERENCE_DIR) as first,
        mutant_workspace(mutants[1], REFERENCE_DIR) as second,
    ):
        assert first != second


def test_apply_mutant_rejects_snippet_that_is_absent(tmp_path: Path) -> None:
    package = tmp_path / "sciref"
    package.mkdir()
    (package / "mod.py").write_text("a = 1\n", encoding="utf-8")

    spec = _spec(original="zzz")

    with pytest.raises(MutantApplyError, match="found 0 times"):
        apply_mutant(spec, package)


def test_apply_mutant_rejects_ambiguous_snippet(tmp_path: Path) -> None:
    package = tmp_path / "sciref"
    package.mkdir()
    (package / "mod.py").write_text("a = 1\nb = 1\n", encoding="utf-8")

    spec = _spec(original="= 1", mutated="= 2")

    with pytest.raises(MutantApplyError, match="found 2 times"):
        apply_mutant(spec, package)


def test_load_catalog_rejects_duplicate_ids(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    entry = "  - {id: M01, function: f, original: a, mutated: b}\n"
    catalog.write_text("mutants:\n" + entry + entry, encoding="utf-8")

    with pytest.raises(MutantApplyError, match="duplicate mutant ids"):
        load_catalog(catalog)


def test_load_catalog_rejects_entry_without_mutated(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("mutants:\n  - {id: M01, function: f, original: a}\n", encoding="utf-8")

    with pytest.raises(MutantApplyError, match="malformed mutant entry"):
        load_catalog(catalog)
