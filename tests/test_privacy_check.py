from __future__ import annotations

from scripts.privacy_check import PROJECT_ROOT, scan_repository


def test_repository_passes_privacy_control() -> None:
    findings, files_scanned, text_files_scanned = scan_repository(PROJECT_ROOT)

    assert files_scanned > 0
    assert text_files_scanned > 0
    assert findings == []


def test_repository_contains_no_persistent_data_artifacts() -> None:
    blocked_suffixes = {".db", ".sqlite", ".sqlite3", ".log"}
    artifacts = [
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and not any(part in {".venv", "venv"} for part in path.relative_to(PROJECT_ROOT).parts)
        and path.suffix.casefold() in blocked_suffixes
    ]
    assert artifacts == []
