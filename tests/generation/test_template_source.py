"""Tests for TemplateProposalSource and Jinja2 templates (CG-07)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from codeguard.adapters.generation import (
    DEFAULT_REL_TOL,
    FileProposalWriter,
    TemplateProposalSource,
)
from codeguard.adapters.generation.template_source import _slugify
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.adapters.validation import AssertionRule, ImportRule, SyntaxRule, TargetRule
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import CaseKind, ContractCase, FunctionContract, ProposalSourceKind

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"


def _load_real_contracts() -> tuple[FunctionContract, ...]:
    return YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR]).load()


def test_generates_at_least_26_proposals_covering_all_functions_and_kinds() -> None:
    contracts = _load_real_contracts()
    proposals = TemplateProposalSource().generate(contracts)

    assert len(proposals) == 46
    assert len(proposals) >= 26
    assert all(proposal.source is ProposalSourceKind.TEMPLATE for proposal in proposals)
    assert all(len(proposal.case_ids) == 1 for proposal in proposals)

    by_function: dict[str, set[CaseKind]] = {}
    case_kind_by_id = {
        (contract.name, case.case_id): case.kind
        for contract in contracts
        for case in contract.cases
    }
    for proposal in proposals:
        case_id = proposal.case_ids[0]
        by_function.setdefault(proposal.target_function, set()).add(
            case_kind_by_id[(proposal.target_function, case_id)]
        )

    assert set(by_function) == {
        "weighted_mean",
        "clamp",
        "normalize_minmax",
        "moving_average",
        "threshold_crossings",
        "validate_range",
    }
    for func_name, kinds in by_function.items():
        expected = (
            {CaseKind.NORMAL, CaseKind.BOUNDARY}
            if func_name == "threshold_crossings"
            else {CaseKind.NORMAL, CaseKind.BOUNDARY, CaseKind.INVALID}
        )
        assert kinds == expected


def test_generation_is_deterministic() -> None:
    contracts = _load_real_contracts()
    source = TemplateProposalSource()

    first = source.generate(contracts)
    second = source.generate(contracts)

    assert first == second


def test_selects_expected_template_patterns_for_each_case_class() -> None:
    contracts = _load_real_contracts()
    proposals = {p.case_ids[0]: p for p in TemplateProposalSource().generate(contracts)}

    # Exact normal (bool -> `is True`)
    assert "assert result is True" in proposals["VR-01"].code
    assert "pytest" not in proposals["VR-01"].code

    # Exact boundary (list[int])
    assert "Generated boundary test" in proposals["TC-03"].code
    assert "assert result == [1]" in proposals["TC-03"].code

    # Scalar float and list[float] use pytest.approx with rel=1e-9
    assert DEFAULT_REL_TOL == 1e-9
    assert "assert result == pytest.approx(2.5, rel=1e-9)" in proposals["WM-02"].code
    assert "assert result == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0], rel=1e-9)" in (
        proposals["NM-02"].code
    )

    # Exception cases use pytest.raises and handle NaN safely
    assert "with pytest.raises(ValueError):" in proposals["WM-05"].code
    assert "with pytest.raises(ValueError):" in proposals["VR-08"].code
    assert 'float("nan")' in proposals["VR-08"].code


def test_custom_rel_tol_and_literal_edge_cases() -> None:
    contract = FunctionContract(
        module="sciref.numeric",
        name="custom_fn",
        signature="custom_fn(a, b, c)",
        docstring="Custom contract",
        cases=(
            ContractCase(
                case_id="C-01",
                kind=CaseKind.NORMAL,
                description='Contains """triple quotes"""\nand newline',
                inputs={"a": float("inf"), "b": float("-inf"), "c": (1,)},
                expected=3.14,
                rel_tol=1e-6,
            ),
            ContractCase(
                case_id="C-02",
                kind=CaseKind.BOUNDARY,
                description="Dict and tuple inputs",
                inputs={"a": {"k": True}, "b": (1, 2), "c": None},
                expected=False,
            ),
        ),
    )

    proposals = TemplateProposalSource().generate([contract])

    assert "pytest.approx(3.14, rel=1e-6)" in proposals[0].code
    assert 'float("inf")' in proposals[0].code
    assert 'float("-inf")' in proposals[0].code
    assert "(1,)" in proposals[0].code
    assert "'''triple quotes'''" in proposals[0].code
    assert "assert result is False" in proposals[1].code
    assert "{'k': True}" in proposals[1].code


def test_all_generated_proposals_pass_validation_chain() -> None:
    contracts = _load_real_contracts()
    proposals = TemplateProposalSource().generate(contracts)
    chain = ValidationChain(
        [
            SyntaxRule(),
            ImportRule(search_paths=[REFERENCE_DIR]),
            TargetRule(contracts),
            AssertionRule(),
        ]
    )

    verdicts = chain.validate_all(proposals)

    rejected = [
        (verdict.proposal_id, verdict.reason, verdict.detail)
        for verdict in verdicts
        if not verdict.valid
    ]
    assert rejected == []


def test_all_generated_files_pass_pytest_against_sciref(tmp_path: Path) -> None:
    contracts = _load_real_contracts()
    proposals = TemplateProposalSource().generate(contracts)
    proposals_dir = tmp_path / "proposals"
    FileProposalWriter().write(proposals, proposals_dir)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REFERENCE_DIR)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(proposals_dir)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "46 passed" in result.stdout


def test_invalid_rel_tol_raises_value_error() -> None:
    with pytest.raises(ValueError, match="rel_tol"):
        TemplateProposalSource(rel_tol=-1e-9)
    with pytest.raises(ValueError, match="rel_tol"):
        TemplateProposalSource(rel_tol=float("nan"))


def test_custom_templates_dir_is_supported(tmp_path: Path) -> None:
    template_names = (
        "test_normal.py.j2",
        "test_boundary.py.j2",
        "test_float.py.j2",
        "test_exception.py.j2",
    )
    for name in template_names:
        (tmp_path / name).write_text(
            "def test_{{ target_function }}_{{ case_slug }}() -> None:\n    assert True\n",
            encoding="utf-8",
        )
    contract = FunctionContract(
        module="sciref.numeric",
        name="clamp",
        signature="clamp(x, lo, hi)",
        docstring="Clamp",
        cases=(
            ContractCase(
                case_id="CL-01",
                kind=CaseKind.NORMAL,
                description="custom",
                inputs={"x": 1, "lo": 0, "hi": 2},
                expected=1,
            ),
        ),
    )

    proposals = TemplateProposalSource(templates_dir=tmp_path).generate([contract])

    assert proposals[0].code == "def test_clamp_cl_01() -> None:\n    assert True\n"


def test_slugify_rejects_symbol_only_case_id() -> None:
    with pytest.raises(ValueError, match="valid identifier slug"):
        _slugify("!!!")
