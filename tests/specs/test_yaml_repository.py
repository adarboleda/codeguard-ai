"""Unit and integration tests for YamlSpecRepository and ListContracts (CG-06)."""

import math
from pathlib import Path

import pytest

from codeguard.adapters.specs import YamlSpecRepository
from codeguard.application.list_specs import ListContracts
from codeguard.domain import CaseKind, ContractCase, FunctionContract, SpecError

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
REFERENCE_DIR = REPO_ROOT / "reference"


def _write_yaml(tmp_path: Path, content: str, name: str = "contracts.yaml") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _make_fake_pkg(tmp_path: Path, body: str, pkg_name: str = "fake_ref") -> tuple[Path, str]:
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "mod.py").write_text(body, encoding="utf-8")
    return tmp_path, pkg_name


def test_loads_real_contracts_and_verifies_sciref_signatures() -> None:
    repo = YamlSpecRepository(CONTRACTS_PATH, search_paths=[REFERENCE_DIR])

    contracts = repo.load()

    assert len(contracts) == 6
    assert sum(len(c.cases) for c in contracts) == 46
    assert [c.qualified_name for c in contracts] == [
        "sciref.numeric.weighted_mean",
        "sciref.numeric.clamp",
        "sciref.numeric.normalize_minmax",
        "sciref.signals.moving_average",
        "sciref.signals.threshold_crossings",
        "sciref.validation.validate_range",
    ]

    by_id = {case.case_id: case for contract in contracts for case in contract.cases}
    assert by_id["CL-04"].expected == 0.0
    assert by_id["VR-02"].expected is False
    assert by_id["TC-02"].expected == []
    assert by_id["VR-08"].expects_exception is True
    assert by_id["VR-08"].expected_exception == "ValueError"
    nan_input = by_id["VR-08"].inputs["value"]
    assert isinstance(nan_input, float) and math.isnan(nan_input)


def test_list_contracts_use_case_uses_injected_repository() -> None:
    expected = (
        FunctionContract(
            module="sciref.numeric",
            name="clamp",
            signature="clamp(x, lo, hi)",
            docstring="Clamp value",
            cases=(
                ContractCase(
                    case_id="C-1",
                    kind=CaseKind.NORMAL,
                    description="Midpoint",
                    inputs={"x": 5, "lo": 0, "hi": 10},
                    expected=5.0,
                ),
            ),
        ),
    )

    class _FakeRepo:
        def load(self) -> tuple[FunctionContract, ...]:
            return expected

    assert ListContracts(_FakeRepo()).execute() == expected


def test_missing_or_directory_spec_path_raises_spec_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(SpecError, match="not found"):
        YamlSpecRepository(missing, verify_signatures=False).load()

    with pytest.raises(SpecError, match="directory"):
        YamlSpecRepository(tmp_path, verify_signatures=False).load()


def test_invalid_yaml_syntax_or_non_mapping_root_raises_spec_error(tmp_path: Path) -> None:
    bad_syntax = _write_yaml(tmp_path, "version: [unclosed\n", "bad.yaml")
    with pytest.raises(SpecError, match="Failed to parse YAML"):
        YamlSpecRepository(bad_syntax, verify_signatures=False).load()

    list_root = _write_yaml(tmp_path, "- item1\n- item2\n", "list.yaml")
    with pytest.raises(SpecError, match="mapping at root level"):
        YamlSpecRepository(list_root, verify_signatures=False).load()


@pytest.mark.parametrize(
    ("yaml_text", "expected_fragment"),
    [
        (
            """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    contract: "Clamp"
    cases:
      - id: CL-1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
""",
            "functions.0.signature",
        ),
        (
            """
version: 1
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: CL-1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
""",
            "package",
        ),
        (
            """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    unknown_field: 123
    cases:
      - id: CL-1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
""",
            "unknown_field",
        ),
        (
            """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: CL-1
        kind: weird
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
""",
            "invalid case kind",
        ),
        (
            """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: CL-1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        raises: ValueError
        oracle: "mid"
""",
            "both 'expected' and 'raises'",
        ),
        (
            """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: CL-1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        oracle: "mid"
""",
            "either 'expected' or 'raises'",
        ),
    ],
)
def test_schema_validation_errors_raise_clear_spec_error(
    tmp_path: Path, yaml_text: str, expected_fragment: str
) -> None:
    path = _write_yaml(tmp_path, yaml_text)
    with pytest.raises(SpecError, match=expected_fragment):
        YamlSpecRepository(path, verify_signatures=False).load()


def test_duplicate_function_and_duplicate_case_raise_spec_error(tmp_path: Path) -> None:
    dup_fn = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: C1
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp duplicate"
    cases:
      - id: C2
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
""",
        "dup_fn.yaml",
    )
    with pytest.raises(SpecError, match="Duplicate function contract"):
        YamlSpecRepository(dup_fn, verify_signatures=False).load()

    dup_case = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x, lo, hi)"
    contract: "Clamp"
    cases:
      - id: SAME
        kind: normal
        inputs: {x: 1, lo: 0, hi: 2}
        expected: 1
        oracle: "mid"
      - id: SAME
        kind: frontera
        inputs: {x: 0, lo: 0, hi: 2}
        expected: 0
        oracle: "edge"
""",
        "dup_case.yaml",
    )
    with pytest.raises(SpecError, match="duplicate case_id"):
        YamlSpecRepository(dup_case, verify_signatures=False).load()


def test_signature_verification_rejects_missing_module_or_function(tmp_path: Path) -> None:
    missing_mod = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: foo
    module: nonexistent_mod
    signature: "foo(x)"
    contract: "Missing module"
    cases:
      - id: F1
        kind: normal
        inputs: {x: 1}
        expected: 1
        oracle: "identity"
""",
        "missing_mod.yaml",
    )
    with pytest.raises(SpecError, match="Cannot import module"):
        YamlSpecRepository(missing_mod, search_paths=[REFERENCE_DIR]).load()

    missing_fn = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: does_not_exist
    module: numeric
    signature: "does_not_exist(x)"
    contract: "Missing fn"
    cases:
      - id: F1
        kind: normal
        inputs: {x: 1}
        expected: 1
        oracle: "identity"
""",
        "missing_fn.yaml",
    )
    with pytest.raises(SpecError, match="does not exist in module"):
        YamlSpecRepository(missing_fn, search_paths=[REFERENCE_DIR]).load()


@pytest.mark.parametrize(
    ("signature", "inputs_yaml", "match_pattern"),
    [
        ("fn(broken", "{a: 1, b: 2}", "Invalid signature syntax"),
        ("other_name(a, b=True)", "{a: 1, b: 2}", "does not match function name"),
        ("fn(a, c=True)", "{a: 1, b: 2}", "Signature mismatch"),
        ("fn(a, b)", "{a: 1, b: 2}", "Default value mismatch"),
        ("fn(a, b=False)", "{a: 1, b: 2}", "Default value mismatch"),
        ("fn(a, b=True)", "{a: 1, wrong: 2}", "do not match signature"),
    ],
)
def test_signature_verification_rejects_mismatches_and_bad_case_inputs(
    tmp_path: Path, signature: str, inputs_yaml: str, match_pattern: str
) -> None:
    search_root, pkg = _make_fake_pkg(
        tmp_path,
        "def fn(a: int, b: bool = True) -> int:\n    return a\n",
        pkg_name="fake_sig_pkg",
    )
    spec_file = _write_yaml(
        tmp_path,
        f"""
version: 1
package: {pkg}
functions:
  - name: fn
    module: mod
    signature: "{signature}"
    contract: "Test function"
    cases:
      - id: T-01
        kind: normal
        inputs: {inputs_yaml}
        expected: 1
        oracle: "test"
""",
    )

    with pytest.raises(SpecError, match=match_pattern):
        YamlSpecRepository(spec_file, search_paths=[search_root]).load()


def test_schema_rejects_blank_identifiers_blank_raises_and_negative_rel_tol(tmp_path: Path) -> None:
    bad_id = _write_yaml(
        tmp_path,
        """
version: 1
package: "   "
functions:
  - name: clamp
    module: sciref.numeric
    signature: "clamp(x)"
    contract: "Clamp"
    cases:
      - id: C1
        kind: normal
        inputs: {x: 1}
        expected: 1
        oracle: "ok"
""",
        "blank_pkg.yaml",
    )
    with pytest.raises(SpecError, match="must not be empty"):
        YamlSpecRepository(bad_id, verify_signatures=False).load()

    bad_raises = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x)"
    contract: "Clamp"
    cases:
      - id: C1
        kind: invalido
        inputs: {x: 1}
        raises: "  "
        oracle: "ok"
""",
        "blank_raises.yaml",
    )
    with pytest.raises(SpecError, match="'raises' must be a non-empty"):
        YamlSpecRepository(bad_raises, verify_signatures=False).load()

    bad_tol = _write_yaml(
        tmp_path,
        """
version: 1
package: sciref
functions:
  - name: clamp
    module: numeric
    signature: "clamp(x)"
    contract: "Clamp"
    cases:
      - id: C1
        kind: normal
        inputs: {x: 1}
        expected: 1
        rel_tol: -0.1
        oracle: "ok"
""",
        "neg_tol.yaml",
    )
    with pytest.raises(SpecError, match="'rel_tol' must be non-negative"):
        YamlSpecRepository(bad_tol, verify_signatures=False).load()


def test_qualified_module_kwonly_and_nonliteral_defaults(tmp_path: Path) -> None:
    search_root, pkg = _make_fake_pkg(
        tmp_path,
        "_SENTINEL = object()\n"
        "def fn(a: int, *, flag: bool = False, tag: object = _SENTINEL) -> int:\n"
        "    return a\n",
        pkg_name="fake_kw_pkg",
    )
    spec_file = _write_yaml(
        tmp_path,
        f"""
version: 1
package: {pkg}
functions:
  - name: fn
    module: {pkg}.mod
    signature: "fn(a, *, flag=False, tag=_SENTINEL)"
    contract: "Keyword-only function"
    cases:
      - id: K-01
        kind: normal
        inputs: {{a: 2}}
        expected: 2
        oracle: "returns a"
""",
    )

    contracts = YamlSpecRepository(spec_file, search_paths=[search_root]).load()
    assert contracts[0].module == f"{pkg}.mod"

    no_sig = YamlSpecRepository(spec_file, verify_signatures=False).load()
    assert len(no_sig) == 1
