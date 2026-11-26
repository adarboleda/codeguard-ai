"""Classify each catalog mutant as KILLED, SURVIVED, EQUIVALENT or INVALID (CG-18).

The baseline (the unmutated package) must be green first. Each mutant then runs the
same test files against its own temporary copy. Only a failing test with a node id
counts as KILLED. Errors (import, collection, setup), timeouts and runs that execute
nothing are INVALID and never count as detections.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

from codeguard.adapters.mutation.applier import MutantSiteError, MutantSpec, mutant_workspace
from codeguard.domain import MutantResult, MutantStatus
from codeguard.domain.errors import CodeGuardError
from codeguard.domain.execution import ExecutionOutcome, SuiteResult
from codeguard.ports.execution import SuiteRunner


class BaselineNotGreenError(CodeGuardError):
    """The unmutated package does not pass its tests, so mutant results would be meaningless."""


def evaluate_mutants(
    specs: Iterable[MutantSpec],
    reference_dir: Path,
    test_files: Sequence[Path],
    runner: SuiteRunner,
    output_dir: Path,
) -> tuple[MutantResult, ...]:
    """Return one ``MutantResult`` per spec, in the order given.

    Raises ``BaselineNotGreenError`` before any mutant runs if the baseline is not green.
    """
    baseline = runner.run(test_files, reference_dir, output_dir / "baseline")
    if not baseline.is_green:
        raise BaselineNotGreenError(f"la línea base no está verde: {_describe(baseline)}")
    return tuple(
        _evaluate_one(spec, reference_dir, test_files, runner, output_dir) for spec in specs
    )


def classify(mutant_id: str, result: SuiteResult) -> MutantResult:
    """Map one suite run against a mutant to its status."""
    if result.timed_out:
        return _invalid(mutant_id, "tiempo agotado; no cuenta como detección", result)
    if result.total == 0:
        return _invalid(mutant_id, "pytest no ejecutó ninguna prueba", result)
    errors = result.count(ExecutionOutcome.ERROR)
    if errors:
        detail = f"{errors} prueba(s) con error de importación, colección o preparación"
        return _invalid(mutant_id, f"{detail}; no cuenta como detección", result)
    killed_by = tuple(
        test.node_id for test in result.tests if test.outcome is ExecutionOutcome.FAILED
    )
    if killed_by:
        return MutantResult(
            mutant_id=mutant_id,
            status=MutantStatus.KILLED,
            killed_by=killed_by,
            duration_seconds=result.duration_seconds,
            detail="detectado por fallo de prueba",
        )
    if result.is_green:
        return MutantResult(
            mutant_id=mutant_id,
            status=MutantStatus.SURVIVED,
            duration_seconds=result.duration_seconds,
            detail="ninguna prueba falló con el mutante",
        )
    return _invalid(mutant_id, f"pytest terminó con código {result.exit_code} sin fallos", result)


def _evaluate_one(
    spec: MutantSpec,
    reference_dir: Path,
    test_files: Sequence[Path],
    runner: SuiteRunner,
    output_dir: Path,
) -> MutantResult:
    if spec.equivalent:
        return MutantResult(
            mutant_id=spec.id,
            status=MutantStatus.EQUIVALENT,
            detail="marcado como equivalente en el catálogo; no se ejecuta",
        )
    try:
        with mutant_workspace(spec, reference_dir) as root:
            result = runner.run(test_files, root, output_dir / spec.id)
    except MutantSiteError as error:
        return MutantResult(mutant_id=spec.id, status=MutantStatus.INVALID, detail=str(error))
    return classify(spec.id, result)


def _invalid(mutant_id: str, detail: str, result: SuiteResult) -> MutantResult:
    return MutantResult(
        mutant_id=mutant_id,
        status=MutantStatus.INVALID,
        duration_seconds=result.duration_seconds,
        detail=detail,
    )


def _describe(result: SuiteResult) -> str:
    if result.timed_out:
        return "tiempo agotado"
    if result.total == 0:
        return "no se ejecutó ninguna prueba"
    return f"{result.failed} fallidas, {result.errors} con error"
