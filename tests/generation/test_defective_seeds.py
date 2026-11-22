"""Tests for defective seeds, case_id traceability, and PA 03 ledger rejection (CG-08)."""

from pathlib import Path

import pytest

from codeguard.adapters.generation import (
    CompositeProposalSource,
    DefectiveSeedProposalSource,
    TemplateProposalSource,
)
from codeguard.adapters.ledger import JsonlLedger
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.adapters.validation import AssertionRule, ImportRule, SyntaxRule, TargetRule
from codeguard.application.validate_proposals import ValidateProposals
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import ProposalSourceKind, RejectionReason, SpecError
from codeguard.domain.ledger import ProposalStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"


def test_loads_two_defective_seeds_with_case_traceability() -> None:
    contracts = YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR]).load()
    known_case_ids = {case.case_id for contract in contracts for case in contract.cases}

    seeds = DefectiveSeedProposalSource(SEEDS_PATH).generate(contracts)

    assert len(seeds) == 2
    assert [seed.proposal_id for seed in seeds] == ["SEED-SYNTAX-01", "SEED-TAUTOLOGY-01"]
    assert all(seed.source is ProposalSourceKind.DEFECTIVE_SEED for seed in seeds)
    assert seeds[0].case_ids == ("WM-01",)
    assert seeds[1].case_ids == ("CL-01",)
    assert all(set(seed.case_ids) <= known_case_ids for seed in seeds)


def test_pa03_both_defective_seeds_enter_denominator_and_are_rejected_in_ledger(
    tmp_path: Path,
) -> None:
    contracts = YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR]).load()
    known_case_ids = {case.case_id for contract in contracts for case in contract.cases}
    source = CompositeProposalSource(
        [TemplateProposalSource(), DefectiveSeedProposalSource(SEEDS_PATH)]
    )
    proposals = source.generate(contracts)

    assert len(proposals) == 48
    assert all(proposal.case_ids for proposal in proposals)
    assert all(set(proposal.case_ids) <= known_case_ids for proposal in proposals)

    chain = ValidationChain(
        [
            SyntaxRule(),
            ImportRule(search_paths=[REFERENCE_DIR]),
            TargetRule(contracts),
            AssertionRule(),
        ]
    )
    report = ValidateProposals(chain, JsonlLedger()).execute(proposals, tmp_path / "pa03-run")
    persisted = JsonlLedger().read(report.ledger_path)

    assert persisted == report.entries
    assert report.summary.total == 48
    assert report.summary.valid == 46
    assert report.summary.rejected == 2
    assert dict(report.summary.by_source) == {"defective_seed": 2, "template": 46}
    assert dict(report.summary.valid_by_source) == {"template": 46}
    assert all(entry.case_ids for entry in persisted)

    by_id = {entry.proposal_id: entry for entry in persisted}
    syntax_seed = by_id["SEED-SYNTAX-01"]
    tautology_seed = by_id["SEED-TAUTOLOGY-01"]
    assert syntax_seed.status is ProposalStatus.REJECTED
    assert syntax_seed.reason is RejectionReason.SYNTAX_ERROR
    assert syntax_seed.case_ids == ("WM-01",)
    assert tautology_seed.status is ProposalStatus.REJECTED
    assert tautology_seed.reason is RejectionReason.TAUTOLOGICAL_ASSERTION
    assert tautology_seed.case_ids == ("CL-01",)


def test_missing_or_directory_seeds_path_raises_spec_error(tmp_path: Path) -> None:
    missing_source = DefectiveSeedProposalSource(tmp_path / "missing.yaml")
    dir_source = DefectiveSeedProposalSource(tmp_path)

    with pytest.raises(SpecError, match="not found"):
        missing_source.generate([])

    with pytest.raises(SpecError, match="directory"):
        dir_source.generate([])


def test_invalid_yaml_and_root_type_raise_spec_error(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("seeds: [unclosed", encoding="utf-8")
    bad_yaml_source = DefectiveSeedProposalSource(bad_yaml)

    non_mapping = tmp_path / "list.yaml"
    non_mapping.write_text("- item\n", encoding="utf-8")
    non_mapping_source = DefectiveSeedProposalSource(non_mapping)

    with pytest.raises(SpecError, match="Failed to parse"):
        bad_yaml_source.generate([])

    with pytest.raises(SpecError, match="YAML mapping"):
        non_mapping_source.generate([])


def test_schema_validation_unknown_case_and_duplicate_id_raise_spec_error(
    tmp_path: Path,
) -> None:
    contracts = YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR]).load()

    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text(
        """
version: 1
package: sciref
seeds:
  - id: SEED-BAD
    case_ids: [WM-01]
    target_module: numeric
    target_function: weighted_mean
    file_name: ../escape.py
    expected_reason: SYNTAX_ERROR
    description: bad file name
    code: "def test_x(): pass"
""",
        encoding="utf-8",
    )
    bad_schema_source = DefectiveSeedProposalSource(bad_schema)

    unknown_case = tmp_path / "unknown_case.yaml"
    unknown_case.write_text(
        """
version: 1
package: sciref
seeds:
  - id: SEED-UNKNOWN
    case_ids: [NO-SUCH-CASE]
    target_module: numeric
    target_function: weighted_mean
    file_name: test_seed_unknown.py
    expected_reason: SYNTAX_ERROR
    description: unknown case
    code: "def test_x(): pass"
""",
        encoding="utf-8",
    )
    unknown_case_source = DefectiveSeedProposalSource(unknown_case)

    dup_id = tmp_path / "dup.yaml"
    dup_id.write_text(
        """
version: 1
package: sciref
seeds:
  - id: SAME-SEED
    case_ids: [WM-01]
    target_module: numeric
    target_function: weighted_mean
    file_name: test_seed_one.py
    expected_reason: SYNTAX_ERROR
    description: first
    code: "def test_one(): pass"
  - id: SAME-SEED
    case_ids: [CL-01]
    target_module: numeric
    target_function: clamp
    file_name: test_seed_two.py
    expected_reason: TAUTOLOGICAL_ASSERTION
    description: second
    code: "def test_two(): pass"
""",
        encoding="utf-8",
    )
    dup_id_source = DefectiveSeedProposalSource(dup_id)

    with pytest.raises(SpecError, match="unsafe seed file_name"):
        bad_schema_source.generate(contracts)

    with pytest.raises(SpecError, match="unknown case_id"):
        unknown_case_source.generate(contracts)

    with pytest.raises(SpecError, match="Duplicate seed id"):
        dup_id_source.generate(contracts)


def test_composite_source_requires_at_least_one_source() -> None:
    empty_sources: list[TemplateProposalSource] = []

    with pytest.raises(ValueError, match="at least one source"):
        CompositeProposalSource(empty_sources)
