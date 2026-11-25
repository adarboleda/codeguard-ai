"""Tests for execution hardening: pre/post sciref hash verification and per-process timeouts."""

import ast
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeguard.adapters.config import load_settings
from codeguard.adapters.execution import (
    PytestSubprocessRunner,
    compute_sciref_snapshot,
    verify_sciref_integrity,
)
from codeguard.adapters.ledger import JsonlLedger
from codeguard.adapters.validation import ImportRule
from codeguard.application.run_suite import RunSuite
from codeguard.cli.main import app
from codeguard.domain import IntegrityError, ProposalSourceKind, TestProposal, ValidationVerdict
from codeguard.domain.execution import SuiteResult
from codeguard.domain.ledger import LedgerEntry

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "codeguard"
REFERENCE_DIR = REPO_ROOT / "reference"
CONTRACTS_PATH = REPO_ROOT / "specs" / "contracts.yaml"
SEEDS_PATH = REPO_ROOT / "specs" / "seeds_defective.yaml"
CATALOG_PATH = REPO_ROOT / "mutants" / "catalog.yaml"
SAMPLES_DIR = REPO_ROOT / "samples" / "security"

cli_runner = CliRunner()


def _copy_reference(tmp_path: Path) -> Path:
    ref_copy = tmp_path / "reference"
    shutil.copytree(REFERENCE_DIR, ref_copy)
    return ref_copy


def _valid_proposal_entry(file_name: str = "test_clamp_ok.py") -> LedgerEntry:
    code = (
        "from sciref.numeric import clamp\n\n"
        "def test_ok() -> None:\n"
        "    assert clamp(5, 0, 10) == 5.0\n"
    )
    proposal = TestProposal(
        proposal_id="P-01",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code=code,
        file_name=file_name,
    )
    verdict = ValidationVerdict(proposal.proposal_id, True, None)
    return LedgerEntry.from_validation(proposal, verdict)


def _tamper_numeric(ref_dir: Path) -> None:
    target = ref_dir / "sciref" / "numeric.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")


def test_verify_sciref_integrity_passes_when_unchanged(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)

    with verify_sciref_integrity(ref_copy) as snapshot:
        expected = compute_sciref_snapshot(ref_copy)
        assert snapshot.combined_sha256 == expected.combined_sha256
        assert "sciref/numeric.py" in snapshot.files


def test_verify_sciref_integrity_aborts_if_hash_changes_before_run(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    _tamper_numeric(ref_copy)
    entered = False

    with pytest.raises(IntegrityError, match="before run"), verify_sciref_integrity(ref_copy):
        entered = True

    assert entered is False


@pytest.mark.parametrize("mutation", ["modify", "add", "delete"])
def test_verify_sciref_integrity_aborts_if_hash_changes_during_run(
    tmp_path: Path, mutation: str
) -> None:
    ref_copy = _copy_reference(tmp_path)

    with pytest.raises(IntegrityError, match="after run"), verify_sciref_integrity(ref_copy):
        if mutation == "modify":
            _tamper_numeric(ref_copy)
        elif mutation == "add":
            (ref_copy / "sciref" / "extra.py").write_text("X = 1\n", encoding="utf-8")
        else:
            (ref_copy / "sciref" / "validation.py").unlink()


class _TamperingRunner:
    def run(self, test_files: Sequence[Path], package_root: Path, output_dir: Path) -> SuiteResult:
        _tamper_numeric(package_root)
        return SuiteResult(tests=(), exit_code=0, duration_seconds=0.1)


def test_run_suite_aborts_when_sciref_modified_during_execution(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    ledger_path = JsonlLedger().write([_valid_proposal_entry()], tmp_path)
    proposals_dir = tmp_path / "proposals"
    proposals_dir.mkdir()
    use_case = RunSuite(_TamperingRunner(), JsonlLedger())

    with pytest.raises(IntegrityError, match="hash changed"):
        use_case.execute(ledger_path, proposals_dir, ref_copy, tmp_path / "out")


def test_pytest_runner_aborts_if_sciref_tampered_before_run(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    _tamper_numeric(ref_copy)
    test_file = tmp_path / "test_clamp_ok.py"
    test_file.write_text(
        "from sciref.numeric import clamp\n\n"
        "def test_ok() -> None:\n"
        "    assert clamp(5, 0, 10) == 5.0\n",
        encoding="utf-8",
    )
    runner = PytestSubprocessRunner()
    out_dir = tmp_path / "out"

    with pytest.raises(IntegrityError, match="before run"):
        runner.run([test_file], ref_copy, out_dir)


def test_cli_run_aborts_with_exit_1_when_sciref_hash_changed(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    out_dir = tmp_path / "out"

    gen = cli_runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
            "--run-id",
            "tamper-run",
        ],
    )
    assert gen.exit_code == 0, gen.output

    val = cli_runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "tamper-run",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
        ],
    )
    assert val.exit_code == 0, val.output

    _tamper_numeric(ref_copy)

    res = cli_runner.invoke(
        app,
        [
            "run",
            "--run-id",
            "tamper-run",
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
        ],
    )
    assert res.exit_code == 1
    assert "sciref integrity check failed" in res.output


def test_cli_all_aborts_with_exit_1_when_sciref_hash_changed(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    _tamper_numeric(ref_copy)

    res = cli_runner.invoke(
        app,
        [
            "all",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--catalog",
            str(CATALOG_PATH),
            "--scan-target",
            str(SAMPLES_DIR),
            "--out",
            str(tmp_path / "out"),
            "--run-id",
            "tamper-all",
        ],
    )
    assert res.exit_code == 1
    assert "sciref integrity check failed" in res.output


def test_all_subprocess_calls_in_src_enforce_explicit_timeout() -> None:
    subprocess_methods = {"run", "Popen", "call", "check_call", "check_output"}
    violations: list[str] = []

    for py_file in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
                and func.attr in subprocess_methods
            ):
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                if not has_timeout:
                    rel = py_file.relative_to(REPO_ROOT).as_posix()
                    violations.append(f"{rel}:{node.lineno} subprocess.{func.attr}()")

    assert violations == []


def test_import_timeout_is_configurable_via_settings_and_validate_cli(tmp_path: Path) -> None:
    config = tmp_path / "codeguard.toml"
    config.write_text(
        "[runner]\ntimeout_seconds = 30\nimport_timeout_seconds = 5\n",
        encoding="utf-8",
    )

    settings = load_settings(config, required=True)
    assert settings.runner.timeout_seconds == 30.0
    assert settings.runner.import_timeout_seconds == 5.0

    bad = cli_runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "x",
            "--out",
            str(tmp_path),
            "--timeout",
            "0",
        ],
    )
    assert bad.exit_code == 1
    assert "timeout_seconds must be positive" in bad.output


def test_run_config_records_both_timeouts(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    config = tmp_path / "codeguard.toml"
    config.write_text(
        "[runner]\ntimeout_seconds = 45\nimport_timeout_seconds = 7\n",
        encoding="utf-8",
    )

    res = cli_runner.invoke(
        app,
        [
            "all",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(REFERENCE_DIR),
            "--catalog",
            str(CATALOG_PATH),
            "--scan-target",
            str(SAMPLES_DIR),
            "--out",
            str(out_dir),
            "--config",
            str(config),
            "--run-id",
            "timeouts-cfg",
        ],
    )
    assert res.exit_code == 0, res.output
    config_text = (out_dir / "timeouts-cfg" / "run_config.json").read_text(encoding="utf-8")
    run_config = json.loads(config_text)
    assert run_config["timeouts"] == {
        "runner_timeout_seconds": 45.0,
        "import_timeout_seconds": 7.0,
    }


def test_import_rule_executes_against_temporary_copy_never_original_reference(
    tmp_path: Path,
) -> None:
    ref_copy = _copy_reference(tmp_path)
    before = compute_sciref_snapshot(ref_copy)
    proposal = TestProposal(
        proposal_id="P-IMPORT-WRITE",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code=(
            "from pathlib import Path\n"
            "import sciref.numeric\n"
            "Path(sciref.numeric.__file__).write_text('# hijacked\\n', encoding='utf-8')\n"
        ),
        file_name="test_import_write.py",
    )

    verdict = ImportRule(search_paths=[ref_copy]).check(proposal)

    assert verdict is None
    assert compute_sciref_snapshot(ref_copy) == before


def test_import_rule_aborts_if_sciref_tampered_before_check(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    _tamper_numeric(ref_copy)
    proposal = TestProposal(
        proposal_id="P-IMPORT-TAMPER",
        target_module="sciref.numeric",
        target_function="clamp",
        source=ProposalSourceKind.TEMPLATE,
        code="from sciref.numeric import clamp\n",
        file_name="test_import_tamper.py",
    )
    rule = ImportRule(search_paths=[ref_copy])

    with pytest.raises(IntegrityError, match="before run"):
        rule.check(proposal)


def test_pytest_runner_isolates_test_writing_to_sciref_file(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    before = compute_sciref_snapshot(ref_copy)
    test_file = tmp_path / "test_write_sciref.py"
    test_file.write_text(
        "from pathlib import Path\n"
        "import sciref.numeric\n\n"
        "def test_writes_copy() -> None:\n"
        "    Path(sciref.numeric.__file__).write_text('# hijacked\\n', encoding='utf-8')\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = PytestSubprocessRunner().run([test_file], ref_copy, tmp_path / "out")

    assert result.is_green
    assert compute_sciref_snapshot(ref_copy) == before


def test_cli_validate_aborts_with_exit_1_when_sciref_hash_changed(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    out_dir = tmp_path / "out"
    gen = cli_runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
            "--run-id",
            "tamper-val",
        ],
    )
    assert gen.exit_code == 0, gen.output

    _tamper_numeric(ref_copy)

    res = cli_runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "tamper-val",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
        ],
    )
    assert res.exit_code == 1
    assert "sciref integrity check failed" in res.output


def test_cli_mutate_aborts_with_exit_1_when_sciref_hash_changed(tmp_path: Path) -> None:
    ref_copy = _copy_reference(tmp_path)
    out_dir = tmp_path / "out"
    gen = cli_runner.invoke(
        app,
        [
            "generate",
            "--specs",
            str(CONTRACTS_PATH),
            "--seeds",
            str(SEEDS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
            "--run-id",
            "tamper-mut",
        ],
    )
    assert gen.exit_code == 0, gen.output
    val = cli_runner.invoke(
        app,
        [
            "validate",
            "--run-id",
            "tamper-mut",
            "--specs",
            str(CONTRACTS_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
        ],
    )
    assert val.exit_code == 0, val.output

    _tamper_numeric(ref_copy)

    res = cli_runner.invoke(
        app,
        [
            "mutate",
            "--run-id",
            "tamper-mut",
            "--catalog",
            str(CATALOG_PATH),
            "--reference-dir",
            str(ref_copy),
            "--out",
            str(out_dir),
        ],
    )
    assert res.exit_code == 1
    assert "sciref integrity check failed" in res.output
