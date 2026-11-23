"""Tests for files the static scanner cannot analyse (CG-15)."""

from pathlib import Path

import pytest

from codeguard.adapters.static import ScanError, scan_paths, scan_source


def test_scan_source_raises_scan_error_on_invalid_python() -> None:
    with pytest.raises(ScanError) as info:
        scan_source("def broken(:\n", "broken.py")

    assert info.value.file_path == "broken.py"
    assert "línea 1" in info.value.reason


def test_scan_paths_raises_on_invalid_file_when_no_error_list_given(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(ScanError):
        scan_paths([tmp_path])


def test_scan_paths_collects_invalid_file_and_keeps_scanning(tmp_path: Path) -> None:
    (tmp_path / "a_broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "b_insecure.py").write_text("eval(payload)\n", encoding="utf-8")
    errors: list[ScanError] = []

    findings = scan_paths([tmp_path], errors=errors)

    assert [f.rule_id for f in findings] == ["CG001"]
    assert [Path(e.file_path).name for e in errors] == ["a_broken.py"]


def test_scan_paths_reports_non_utf8_file_as_error(tmp_path: Path) -> None:
    (tmp_path / "latin.py").write_bytes("x = 'ñ'\n".encode("latin-1"))
    errors: list[ScanError] = []

    findings = scan_paths([tmp_path], errors=errors)

    assert findings == ()
    assert len(errors) == 1
    assert "UTF-8" in errors[0].reason


def test_scan_paths_raises_on_non_utf8_file_when_no_error_list_given(tmp_path: Path) -> None:
    (tmp_path / "latin.py").write_bytes("x = 'ñ'\n".encode("latin-1"))

    with pytest.raises(ScanError):
        scan_paths([tmp_path])
