"""JSON Lines ledger: ``out/<run_id>/ledger.jsonl``, one proposal per line (CG-12)."""

import json
from collections.abc import Iterable
from pathlib import Path

from codeguard.domain.ledger import LedgerEntry

LEDGER_FILE_NAME = "ledger.jsonl"


class JsonlLedger:
    """Writes and reads the ledger as UTF-8 JSON Lines with ``\\n`` line endings."""

    def write(self, entries: Iterable[LedgerEntry], run_dir: Path) -> Path:
        """Write every entry (valid and rejected) and return the ledger path."""
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / LEDGER_FILE_NAME
        lines = (json.dumps(entry.to_record(), ensure_ascii=False) for entry in entries)
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")
        return path

    def read(self, path: Path) -> tuple[LedgerEntry, ...]:
        """Read entries back; raise ValueError naming the line if one is malformed."""
        entries: list[LedgerEntry] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("each line must be a JSON object")
                entries.append(LedgerEntry.from_record(record))
            except ValueError as error:  # json.JSONDecodeError is a ValueError
                raise ValueError(f"{path}:{number}: invalid ledger line: {error}") from error
        return tuple(entries)
