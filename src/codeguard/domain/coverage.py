"""Line and branch coverage of the package under study (CG-17, PA 05)."""

from dataclasses import dataclass

_FULL = 100.0


def _pct(covered: int, total: int) -> float:
    """Percentage of ``covered`` over ``total``; nothing to cover counts as 100 %."""
    return _FULL if total == 0 else covered / total * _FULL


@dataclass(frozen=True)
class ModuleCoverage:
    """Coverage of one module, e.g. ``sciref/numeric.py``."""

    path: str
    statements: int
    covered_lines: int
    branches: int
    covered_branches: int
    missing_lines: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("path must not be empty")
        counts = (self.statements, self.covered_lines, self.branches, self.covered_branches)
        if min(counts) < 0:
            raise ValueError("coverage counts must be non-negative")
        if self.covered_lines > self.statements or self.covered_branches > self.branches:
            raise ValueError("covered counts cannot exceed totals")

    @property
    def line_pct(self) -> float:
        return _pct(self.covered_lines, self.statements)

    @property
    def branch_pct(self) -> float:
        return _pct(self.covered_branches, self.branches)


@dataclass(frozen=True)
class CoverageTargets:
    """Minimum line and branch coverage the team committed to (plan, section 1)."""

    min_line_pct: float
    min_branch_pct: float

    def __post_init__(self) -> None:
        for name, value in (
            ("min_line_pct", self.min_line_pct),
            ("min_branch_pct", self.min_branch_pct),
        ):
            if not 0.0 <= value <= _FULL:
                raise ValueError(f"{name} must be between 0 and 100")


@dataclass(frozen=True)
class CoverageReport:
    """Coverage of every measured module, with totals over all of them."""

    modules: tuple[ModuleCoverage, ...]

    @property
    def statements(self) -> int:
        return sum(module.statements for module in self.modules)

    @property
    def covered_lines(self) -> int:
        return sum(module.covered_lines for module in self.modules)

    @property
    def branches(self) -> int:
        return sum(module.branches for module in self.modules)

    @property
    def covered_branches(self) -> int:
        return sum(module.covered_branches for module in self.modules)

    @property
    def line_pct(self) -> float:
        return _pct(self.covered_lines, self.statements)

    @property
    def branch_pct(self) -> float:
        return _pct(self.covered_branches, self.branches)

    def meets(self, targets: CoverageTargets) -> bool:
        """True if both line and branch coverage reach their targets."""
        return self.line_pct >= targets.min_line_pct and self.branch_pct >= targets.min_branch_pct
