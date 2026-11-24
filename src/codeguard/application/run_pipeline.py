"""End-to-end pipeline orchestration, stage runners, and run_config.json (CG-23)."""

import importlib.metadata
import json
import platform
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import yaml

import codeguard
from codeguard.adapters.execution import (
    PytestSubprocessRunner,
    compute_sciref_snapshot,
    verify_sciref_integrity,
)
from codeguard.adapters.execution.junit import parse_junit
from codeguard.adapters.generation import (
    CompositeProposalSource,
    DefectiveSeedProposalSource,
    FileProposalWriter,
    TemplateProposalSource,
)
from codeguard.adapters.ledger import LEDGER_FILE_NAME, JsonlLedger
from codeguard.adapters.mutation import (
    PACKAGE_NAME,
    MutantSpec,
    load_catalog,
    mutant_workspace,
)
from codeguard.adapters.specs import YamlSpecRepository
from codeguard.adapters.static import scan_paths
from codeguard.adapters.validation import AssertionRule, ImportRule, SyntaxRule, TargetRule
from codeguard.adapters.validation.import_rule import (
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_IMPORT_TIMEOUT_SECONDS,
)
from codeguard.application.compute_metrics import ComputeMetrics
from codeguard.application.generate_tests import GenerateTests, GenerationReport
from codeguard.application.run_suite import RunSuite
from codeguard.application.validate_proposals import ValidateProposals, ValidationReport
from codeguard.application.validation_chain import ValidationChain
from codeguard.domain import Finding, FunctionContract, MutantStatus
from codeguard.domain.execution import ExecutionOutcome, SuiteResult
from codeguard.domain.ledger import LedgerSummary
from codeguard.ports.generation import ProposalSource

RUN_CONFIG_FILE_NAME = "run_config.json"
MUTANTS_FILE_NAME = "mutants.json"
FINDINGS_FILE_NAME = "findings.json"
SUMMARY_FILE_NAME = "summary.json"
DEFAULT_SEED = 42


@dataclass(frozen=True)
class MutantOutcome:
    """Execution outcome for a single catalog mutant."""

    mutant_id: str
    function: str
    status: str
    exit_code: int | None
    timed_out: bool
    failed: int
    duration_seconds: float


@dataclass(frozen=True)
class MutationReport:
    """Aggregated outcome of running the suite across all catalog mutants."""

    outcomes: tuple[MutantOutcome, ...]
    output_path: Path

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def killed(self) -> int:
        return sum(1 for item in self.outcomes if item.status == "KILLED")

    @property
    def survived(self) -> int:
        return sum(1 for item in self.outcomes if item.status == "SURVIVED")

    @property
    def equivalent(self) -> int:
        return sum(1 for item in self.outcomes if item.status == MutantStatus.EQUIVALENT.value)

    @property
    def invalid(self) -> int:
        return sum(1 for item in self.outcomes if item.status == MutantStatus.INVALID.value)

    @property
    def timed_out_count(self) -> int:
        return sum(1 for item in self.outcomes if item.timed_out)


@dataclass(frozen=True)
class ScanReport:
    """Result of running static security rules over target paths."""

    findings: tuple[Finding, ...]
    output_path: Path


@dataclass(frozen=True)
class SummaryReport:
    """Consolidated summary report written to ``summary.json``."""

    run_id: str
    summary_path: Path
    data: Mapping[str, object]


@dataclass(frozen=True)
class PipelineOptions:
    """Parameters governing a full reproducible ``codeguard all`` run."""

    run_id: str
    specs_path: Path
    seeds_path: Path
    include_seeds: bool
    reference_dir: Path
    catalog_path: Path
    scan_targets: tuple[Path, ...]
    out_dir: Path
    timeout_seconds: float
    seed: int = DEFAULT_SEED
    import_timeout_seconds: float = DEFAULT_IMPORT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class PipelineResult:
    """Summary metrics and artifact locations produced by ``RunPipeline``."""

    run_id: str
    run_dir: Path
    run_config_path: Path
    summary_path: Path
    proposals_total: int
    proposals_valid: int
    proposals_rejected: int
    baseline_passed: int
    baseline_failed: int
    mutants_killed: int
    mutants_total: int
    findings_total: int
    phase_durations_seconds: Mapping[str, float]


def run_mutation_stage(
    run_dir: Path,
    catalog_path: Path,
    reference_dir: Path,
    timeout_seconds: float,
) -> MutationReport:
    """Evaluate all mutants in ``catalog_path`` against the validated suite."""
    ledger_path = run_dir / LEDGER_FILE_NAME
    if not ledger_path.is_file():
        raise ValueError(f"ledger not found: {ledger_path}; run 'codeguard validate' first")
    if not catalog_path.is_file():
        raise ValueError(f"mutant catalog not found: {catalog_path}")
    if not (reference_dir / PACKAGE_NAME).is_dir():
        raise ValueError(f"reference package not found: {reference_dir / PACKAGE_NAME}")

    specs = load_catalog(catalog_path)
    equivalent_ids = _load_equivalent_mutant_ids(catalog_path)
    runner = PytestSubprocessRunner(timeout_seconds)
    ledger = JsonlLedger()
    with verify_sciref_integrity(reference_dir):
        outcomes = tuple(
            _evaluate_single_mutant(
                spec, run_dir, ledger_path, reference_dir, runner, ledger, equivalent_ids
            )
            for spec in specs
        )
    output_path = run_dir / MUTANTS_FILE_NAME
    payload = [asdict(item) for item in outcomes]
    _write_json(output_path, payload)
    return MutationReport(outcomes=outcomes, output_path=output_path)


def run_scan_stage(run_dir: Path, targets: Sequence[Path]) -> ScanReport:
    """Run static security rules over ``targets`` and persist ``findings.json``."""
    if not targets:
        raise ValueError("at least one scan target is required")
    missing = [str(target) for target in targets if not target.exists()]
    if missing:
        raise ValueError(f"scan target(s) not found: {', '.join(missing)}")

    run_dir.mkdir(parents=True, exist_ok=True)
    findings = scan_paths(targets)
    output_path = run_dir / FINDINGS_FILE_NAME
    payload = [_finding_to_dict(item) for item in findings]
    _write_json(output_path, payload)
    return ScanReport(findings=findings, output_path=output_path)


def build_summary_report(run_dir: Path) -> SummaryReport:
    """Consolidate available artifacts in ``run_dir`` into ``summary.json``."""
    if not run_dir.is_dir():
        raise ValueError(f"run directory not found: {run_dir}")

    payload: dict[str, object] = {
        "run_id": run_dir.name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    _attach_run_config_summary(payload, run_dir / RUN_CONFIG_FILE_NAME)
    _attach_ledger_summary(payload, run_dir / LEDGER_FILE_NAME)
    _attach_junit_summary(payload, run_dir / "junit.xml")
    _attach_mutants_summary(payload, run_dir / MUTANTS_FILE_NAME)
    _attach_findings_summary(payload, run_dir / FINDINGS_FILE_NAME)

    summary_path = run_dir / SUMMARY_FILE_NAME
    _write_json(summary_path, payload)
    ComputeMetrics().execute(run_dir)
    return SummaryReport(
        run_id=run_dir.name,
        summary_path=summary_path,
        data=MappingProxyType(payload),
    )


def write_run_config(
    options: PipelineOptions,
    run_dir: Path,
    phase_durations: Mapping[str, float],
) -> Path:
    """Persist reproducibility metadata to ``out/<run_id>/run_config.json``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "run_id": options.run_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "seed": options.seed,
        "versions": _collect_versions(),
        "timeouts": {
            "runner_timeout_seconds": options.timeout_seconds,
            "import_timeout_seconds": options.import_timeout_seconds,
        },
        "sciref_sha256": _compute_sciref_hashes(options.reference_dir),
        "include_seeds": options.include_seeds,
        "paths": {
            "specs": options.specs_path.as_posix(),
            "seeds": options.seeds_path.as_posix(),
            "reference_dir": options.reference_dir.as_posix(),
            "catalog": options.catalog_path.as_posix(),
            "scan_targets": [path.as_posix() for path in options.scan_targets],
        },
        "phase_durations_seconds": {
            phase: round(duration, 6) for phase, duration in phase_durations.items()
        },
    }
    config_path = run_dir / RUN_CONFIG_FILE_NAME
    _write_json(config_path, payload)
    return config_path


class RunPipeline:
    """Chains generate, validate, run, mutate, scan, and report for ``codeguard all``."""

    def execute(self, options: PipelineOptions) -> PipelineResult:
        """Execute all six stages sequentially and write ``run_config.json``."""
        run_dir = options.out_dir / options.run_id
        durations: dict[str, float] = {}

        with verify_sciref_integrity(options.reference_dir):
            gen_report, durations["generate"] = _timed(
                lambda: self._stage_generate(options, run_dir)
            )
            val_report, durations["validate"] = _timed(
                lambda: self._stage_validate(options, gen_report, run_dir)
            )
            baseline, durations["run"] = _timed(lambda: self._stage_run(options, run_dir))
            if not baseline.is_green:
                raise ValueError("baseline suite failed; aborting mutation stage")

            mut_report, durations["mutate"] = _timed(
                lambda: run_mutation_stage(
                    run_dir, options.catalog_path, options.reference_dir, options.timeout_seconds
                )
            )
            scan_report, durations["scan"] = _timed(
                lambda: run_scan_stage(run_dir, options.scan_targets)
            )

            report_start = time.perf_counter()
            run_config_path = write_run_config(options, run_dir, durations)
            summary = build_summary_report(run_dir)
            durations["report"] = time.perf_counter() - report_start
            write_run_config(options, run_dir, durations)
            ComputeMetrics().execute(run_dir)

        return PipelineResult(
            run_id=options.run_id,
            run_dir=run_dir,
            run_config_path=run_config_path,
            summary_path=summary.summary_path,
            proposals_total=val_report.summary.total,
            proposals_valid=val_report.summary.valid,
            proposals_rejected=val_report.summary.rejected,
            baseline_passed=baseline.passed,
            baseline_failed=baseline.failed + baseline.errors,
            mutants_killed=mut_report.killed,
            mutants_total=mut_report.total,
            findings_total=len(scan_report.findings),
            phase_durations_seconds=MappingProxyType(dict(durations)),
        )

    def _stage_generate(self, options: PipelineOptions, run_dir: Path) -> GenerationReport:
        repository = YamlSpecRepository(
            specs_path=options.specs_path, search_paths=[options.reference_dir]
        )
        source = _build_source(options)
        return GenerateTests(repository, source, FileProposalWriter()).execute(run_dir)

    def _stage_validate(
        self,
        options: PipelineOptions,
        generation: GenerationReport,
        run_dir: Path,
    ) -> ValidationReport:
        contracts = YamlSpecRepository(
            specs_path=options.specs_path, search_paths=[options.reference_dir]
        ).load()
        chain = _validation_chain(contracts, options.reference_dir, options.import_timeout_seconds)
        return ValidateProposals(chain, JsonlLedger()).execute(generation.proposals, run_dir)

    def _stage_run(self, options: PipelineOptions, run_dir: Path) -> SuiteResult:
        runner = PytestSubprocessRunner(options.timeout_seconds)
        report = RunSuite(runner, JsonlLedger()).execute(
            ledger_path=run_dir / LEDGER_FILE_NAME,
            proposals_dir=run_dir / "proposals",
            package_root=options.reference_dir,
            output_dir=run_dir,
        )
        return report.result


def _build_source(options: PipelineOptions) -> ProposalSource:
    template_source = TemplateProposalSource()
    if not options.include_seeds:
        return template_source
    seeds_source = DefectiveSeedProposalSource(options.seeds_path)
    return CompositeProposalSource([template_source, seeds_source])


def _validation_chain(
    contracts: tuple[FunctionContract, ...],
    reference_dir: Path,
    import_timeout_seconds: float = DEFAULT_IMPORT_TIMEOUT_SECONDS,
) -> ValidationChain:
    return ValidationChain(
        [
            SyntaxRule(),
            ImportRule(search_paths=[reference_dir], timeout_seconds=import_timeout_seconds),
            TargetRule(contracts),
            AssertionRule(),
        ]
    )


def _load_equivalent_mutant_ids(catalog_path: Path) -> frozenset[str]:
    raw: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("mutants"), list):
        return frozenset()
    return frozenset(
        str(entry["id"])
        for entry in raw["mutants"]
        if isinstance(entry, dict) and entry.get("status") == "equivalent" and "id" in entry
    )


def _evaluate_single_mutant(
    spec: MutantSpec,
    run_dir: Path,
    ledger_path: Path,
    reference_dir: Path,
    runner: PytestSubprocessRunner,
    ledger: JsonlLedger,
    equivalent_ids: frozenset[str],
) -> MutantOutcome:
    with mutant_workspace(spec, reference_dir) as mutated_root:
        exec_report = RunSuite(runner, ledger).execute(
            ledger_path=ledger_path,
            proposals_dir=run_dir / "proposals",
            package_root=mutated_root,
            output_dir=run_dir / "mutants" / spec.id,
        )
    return _classify_mutant_outcome(spec, exec_report.result, equivalent_ids)


def _classify_mutant_outcome(
    spec: MutantSpec, result: SuiteResult, equivalent_ids: frozenset[str]
) -> MutantOutcome:
    if spec.id in equivalent_ids:
        status = MutantStatus.EQUIVALENT.value
    elif result.timed_out or (result.total == 0 and not result.is_green):
        status = MutantStatus.INVALID.value
    elif not result.is_green:
        status = MutantStatus.KILLED.value
    else:
        status = MutantStatus.SURVIVED.value
    return MutantOutcome(
        mutant_id=spec.id,
        function=spec.function,
        status=status,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        failed=result.failed + result.errors,
        duration_seconds=result.duration_seconds,
    )


def _finding_to_dict(finding: Finding) -> dict[str, object]:
    return {
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "line": finding.line,
        "column": finding.column,
        "snippet": finding.snippet,
        "message": finding.message,
        "recommendation": finding.recommendation,
        "severity": finding.severity.value,
    }


def _collect_versions() -> dict[str, str]:
    versions: dict[str, str] = {
        "codeguard": codeguard.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    for package in ("pytest", "pydantic", "jinja2", "typer", "pyyaml"):
        versions[package] = importlib.metadata.version(package)
    return versions


def _compute_sciref_hashes(reference_dir: Path) -> dict[str, object]:
    package_dir = reference_dir / PACKAGE_NAME
    if not package_dir.is_dir():
        raise ValueError(f"reference package not found: {package_dir}")
    return compute_sciref_snapshot(reference_dir).to_dict()


def _attach_run_config_summary(payload: dict[str, object], path: Path) -> None:
    if not path.is_file():
        return
    raw = _read_json(path)
    if isinstance(raw, dict):
        payload["run_config"] = {
            "seed": raw.get("seed"),
            "sciref_sha256": raw.get("sciref_sha256"),
            "timeouts": raw.get("timeouts"),
        }


def _attach_ledger_summary(payload: dict[str, object], path: Path) -> None:
    if not path.is_file():
        return
    summary = LedgerSummary.from_entries(JsonlLedger().read(path))
    payload["validation"] = {
        "total": summary.total,
        "valid": summary.valid,
        "rejected": summary.rejected,
        "validity_pct": round(summary.validity_pct, 2),
        "by_reason": dict(summary.by_reason),
    }


def _attach_junit_summary(payload: dict[str, object], path: Path) -> None:
    if not path.is_file():
        return
    tests = parse_junit(path)
    payload["execution"] = {
        "total": len(tests),
        "passed": sum(1 for t in tests if t.outcome is ExecutionOutcome.PASSED),
        "failed": sum(1 for t in tests if t.outcome is ExecutionOutcome.FAILED),
        "errors": sum(1 for t in tests if t.outcome is ExecutionOutcome.ERROR),
        "skipped": sum(1 for t in tests if t.outcome is ExecutionOutcome.SKIPPED),
    }


def _attach_mutants_summary(payload: dict[str, object], path: Path) -> None:
    if not path.is_file():
        return
    raw = _read_json(path)
    if isinstance(raw, list):
        killed = sum(1 for item in raw if isinstance(item, dict) and item.get("status") == "KILLED")
        survived = sum(
            1 for item in raw if isinstance(item, dict) and item.get("status") == "SURVIVED"
        )
        equivalent = sum(
            1 for item in raw if isinstance(item, dict) and item.get("status") == "EQUIVALENT"
        )
        invalid = sum(
            1
            for item in raw
            if isinstance(item, dict) and item.get("status") in {"INVALID", "TIMEOUT"}
        )
        payload["mutation"] = {
            "total": len(raw),
            "killed": killed,
            "survived": survived,
            "equivalent": equivalent,
            "invalid": invalid,
        }


def _attach_findings_summary(payload: dict[str, object], path: Path) -> None:
    if not path.is_file():
        return
    raw = _read_json(path)
    if isinstance(raw, list):
        by_rule: dict[str, int] = {}
        for item in raw:
            if isinstance(item, dict):
                rule_id = str(item.get("rule_id", "UNKNOWN"))
                by_rule[rule_id] = by_rule.get(rule_id, 0) + 1
        payload["static_scan"] = {"total": len(raw), "by_rule": by_rule}


def _read_json(path: Path) -> object:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _timed[T](fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    return fn(), time.perf_counter() - start
