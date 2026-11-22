"""Tests for FileProposalWriter manifest.json and FileProposalReader round-trip."""

import json
from pathlib import Path

import pytest

from codeguard.adapters.generation import (
    MANIFEST_FILE_NAME,
    CompositeProposalSource,
    DefectiveSeedProposalSource,
    FileProposalReader,
    FileProposalWriter,
    TemplateProposalSource,
)
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.domain import ProposalSourceKind, TestProposal

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"


def test_writer_and_reader_roundtrip_preserves_all_proposals_and_metadata(tmp_path: Path) -> None:
    contracts = YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR]).load()
    proposals = CompositeProposalSource(
        [TemplateProposalSource(), DefectiveSeedProposalSource(SEEDS_PATH)]
    ).generate(contracts)
    proposals_dir = tmp_path / "proposals"

    FileProposalWriter().write(proposals, proposals_dir)
    loaded = FileProposalReader().read(proposals_dir)

    assert (proposals_dir / MANIFEST_FILE_NAME).is_file()
    assert loaded == proposals


def test_reader_rejects_missing_or_malformed_manifest(tmp_path: Path) -> None:
    reader = FileProposalReader()
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()

    with pytest.raises(ValueError, match="Proposals manifest not found"):
        reader.read(missing_dir)

    bad_json_dir = tmp_path / "bad_json"
    bad_json_dir.mkdir()
    (bad_json_dir / MANIFEST_FILE_NAME).write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid proposals manifest"):
        reader.read(bad_json_dir)

    non_list_dir = tmp_path / "non_list"
    non_list_dir.mkdir()
    (non_list_dir / MANIFEST_FILE_NAME).write_text('{"a": 1}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array of objects"):
        reader.read(non_list_dir)


def test_reader_rejects_invalid_record_unsafe_filename_and_missing_source(tmp_path: Path) -> None:
    reader = FileProposalReader()

    bad_case_ids_dir = tmp_path / "bad_case_ids"
    bad_case_ids_dir.mkdir()
    (bad_case_ids_dir / "test_ok.py").write_text("assert True\n", encoding="utf-8")
    (bad_case_ids_dir / MANIFEST_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "proposal_id": "p-1",
                    "target_module": "sciref.numeric",
                    "target_function": "clamp",
                    "source": ProposalSourceKind.TEMPLATE.value,
                    "case_ids": "CL-01",
                    "file_name": "test_ok.py",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case_ids"):
        reader.read(bad_case_ids_dir)

    unsafe_name_dir = tmp_path / "unsafe_name"
    unsafe_name_dir.mkdir()
    (unsafe_name_dir / MANIFEST_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "proposal_id": "p-1",
                    "target_module": "sciref.numeric",
                    "target_function": "clamp",
                    "source": ProposalSourceKind.TEMPLATE.value,
                    "case_ids": ["CL-01"],
                    "file_name": "../escape.py",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsafe proposal file_name"):
        reader.read(unsafe_name_dir)

    missing_file_dir = tmp_path / "missing_file"
    missing_file_dir.mkdir()
    proposal = TestProposal(
        proposal_id="p-1",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code="assert True\n",
        case_ids=("CL-01",),
        file_name="test_missing.py",
    )
    FileProposalWriter().write([proposal], missing_file_dir)
    (missing_file_dir / "test_missing.py").unlink()

    with pytest.raises(ValueError, match="Proposal source file not found"):
        reader.read(missing_file_dir)

    blank_id_dir = tmp_path / "blank_id"
    blank_id_dir.mkdir()
    (blank_id_dir / "test_ok.py").write_text("assert True\n", encoding="utf-8")
    (blank_id_dir / MANIFEST_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "proposal_id": "",
                    "target_module": "sciref.numeric",
                    "target_function": "clamp",
                    "source": ProposalSourceKind.TEMPLATE.value,
                    "case_ids": ["CL-01"],
                    "file_name": "test_ok.py",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="proposal_id"):
        reader.read(blank_id_dir)
