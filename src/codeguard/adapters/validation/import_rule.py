"""Rule 2 of the validation chain: the proposal must import cleanly (CG-09).

The proposal is imported in a separate Python process, inside a temporary directory
and with a timeout, so its module-level code never runs inside CodeGuard itself
(proposals may come from an LLM).
"""

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from codeguard.domain import RejectionReason, TestProposal, ValidationVerdict

DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_DETAIL_CHARS = 300
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.py$")
_FALLBACK_FILE_NAME = "proposal.py"

# Loads the file as a module named "codeguard_proposal" (not "__main__"), so an
# ``if __name__ == "__main__":`` block in the proposal is not executed.
_IMPORT_SCRIPT = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('codeguard_proposal', sys.argv[1])\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
)


class ImportRule:
    """Rejects proposals whose imports or module-level code fail.

    ``search_paths`` are prepended to ``PYTHONPATH`` in the child process; the
    composition root passes the folder that contains ``sciref`` (``reference/``).
    """

    name = "import"

    def __init__(
        self,
        search_paths: Sequence[Path] = (),
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        python_executable: str = sys.executable,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._search_paths = tuple(Path(path).resolve() for path in search_paths)
        self._timeout_seconds = timeout_seconds
        self._python = python_executable

    def check(self, proposal: TestProposal) -> ValidationVerdict | None:
        """Return ``None`` if the module imports in a subprocess, else ``IMPORT_ERROR``."""
        with tempfile.TemporaryDirectory(prefix="codeguard-import-") as workdir:
            module_path = Path(workdir) / _file_name(proposal)
            module_path.write_text(proposal.code, encoding="utf-8")
            try:
                result = subprocess.run(
                    [self._python, "-c", _IMPORT_SCRIPT, str(module_path)],
                    cwd=workdir,
                    env=self._child_env(),
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return self._reject(proposal, f"timeout after {self._timeout_seconds:g} s")
        if result.returncode != 0:
            return self._reject(proposal, _last_error_line(result.stderr))
        return None

    def _child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        paths = [str(path) for path in self._search_paths]
        if env.get("PYTHONPATH"):
            paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(paths)
        # Do not write __pycache__ into reference/: the package under study is read-only.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def _reject(self, proposal: TestProposal, detail: str) -> ValidationVerdict:
        return ValidationVerdict(
            proposal_id=proposal.proposal_id,
            valid=False,
            reason=RejectionReason.IMPORT_ERROR,
            detail=detail,
            rule_name=self.name,
        )


def _file_name(proposal: TestProposal) -> str:
    """Use the proposal's own file name only if it is a plain, safe ``*.py`` name."""
    if _SAFE_FILE_NAME.match(proposal.file_name):
        return proposal.file_name
    return _FALLBACK_FILE_NAME


def _last_error_line(stderr: str) -> str:
    """Return the final line of a traceback, e.g. ``ModuleNotFoundError: No module ...``."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "import failed without error output"
    return lines[-1][:_MAX_DETAIL_CHARS]
