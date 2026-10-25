"""The experiments checker (experiment-format-v1, task 4.1, spec "The checker").

One test per rule, with the error, warning and information cases for new
and converted records, plus a test that the checker changes no file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.check import Finding, check_experiments, has_failures
from omrs.core.experiment_records.index import INDEX_END, INDEX_START, render_index
from omrs.core.experiment_records.reserved import load_reservations
from omrs.core.experiment_records.run_record import append_run_record
from omrs.core.experiment_records.scan import scan_experiments

_MIGRATION = {"from_status": "PASS", "source": "EXP_README.md", "date": "2026-10-25"}
_COMMIT = "a" * 40


def _record(name: str, **overrides: Any) -> dict[str, Any]:
    number, _, rest = name.partition("-")
    data: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": number,
        "title": f"Experiment {number}",
        "date": name[-10:],
        "category": "retrieval",
        "size": "Quick",
        "status": "PASS",
        "superseded_by": None,
        "finding": "Found.",
    }
    data.update(overrides)
    return data


def make(root: Path, name: str, data: dict[str, Any] | None = None, *files: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if data is not None:
        (folder / "experiment.json").write_text(json.dumps(data), encoding="utf-8")
    for file in files:
        (folder / file).write_text("text\n", encoding="utf-8")
    return folder


def sync_index(root: Path) -> None:
    """Write an EXP_README.md whose block matches the generated one."""
    block = render_index(scan_experiments(root), load_reservations(root))
    (root / "EXP_README.md").write_text(
        f"# Experiments\n\n{INDEX_START}\n{block}{INDEX_END}\n", encoding="utf-8"
    )


def codes(findings: tuple[Finding, ...], folder: str | None = None) -> dict[str, str]:
    """Map code to severity, for one folder or for all findings."""
    return {f.code: f.severity for f in findings if folder is None or f.folder == folder}


def run(root: Path) -> tuple[Finding, ...]:
    sync_index(root)
    return check_experiments(root)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path


_GOOD = "1-good-2026-05-12"


def test_clean_directory_has_no_findings(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    assert run(root) == ()


def test_finding_fields(root: Path) -> None:
    make(root, "2-bare-2026-05-12")
    (finding,) = run(root)
    assert finding == Finding(
        severity="error",
        code="record-missing",
        folder="2-bare-2026-05-12",
        message=finding.message,
    )
    assert "experiment.json" in finding.message


def test_invalid_record_is_an_error(root: Path) -> None:
    name = "2-bad-2026-05-12"
    make(root, name, _record(name, owner="x"), "report.md")
    findings = run(root)
    assert codes(findings, name) == {"record-invalid": "error"}
    assert "owner" in findings[0].message


def test_newer_record_format_is_an_error(root: Path) -> None:
    name = "2-new-2026-05-12"
    make(root, name, _record(name, format="omrs-experiment/2"), "report.md")
    findings = run(root)
    assert codes(findings, name) == {"record-invalid": "error"}
    assert "newer omrs" in findings[0].message


def test_number_differs_from_folder_name(root: Path) -> None:
    name = "2-x-2026-05-12"
    make(root, name, _record(name, number="3"), "report.md")
    assert codes(run(root), name) == {"number-mismatch": "error"}


def test_date_differs_from_folder_name(root: Path) -> None:
    name = "2-x-2026-05-12"
    make(root, name, _record(name, date="2026-05-13"), "report.md")
    assert codes(run(root), name) == {"date-mismatch": "error"}


def test_folder_name_without_pattern_is_a_warning(root: Path) -> None:
    make(root, "Odd Name", _record("2-x-2026-05-12"), "report.md")
    assert codes(run(root), "Odd Name") == {"folder-name": "warning"}


def test_superseding_folder_must_exist(root: Path) -> None:
    name = "2-old-2026-05-12"
    make(
        root,
        name,
        _record(name, status="SUPERSEDED", superseded_by="9-gone-2026-01-01"),
        "report.md",
    )
    findings = run(root)
    assert codes(findings, name) == {"superseded-target-missing": "error"}
    assert "9-gone-2026-01-01" in findings[0].message


def test_existing_superseding_folder_is_fine(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    name = "2-old-2026-05-12"
    make(root, name, _record(name, status="SUPERSEDED", superseded_by=_GOOD), "report.md")
    assert run(root) == ()


def test_shared_number_between_converted_folders_is_a_warning(root: Path) -> None:
    a, b = "19-native-fts-2026-08-29", "19-lancedb-2026-08-21"
    make(root, a, _record(a, migration=_MIGRATION), "report.md")
    make(root, b, _record(b, migration=_MIGRATION), "report.md")
    findings = run(root)
    assert codes(findings, a) == {"number-shared": "warning"}
    assert codes(findings, b) == {"number-shared": "warning"}
    assert b in next(f.message for f in findings if f.folder == a)


def test_shared_number_on_a_new_record_is_an_error(root: Path) -> None:
    old, new = "19-native-fts-2026-08-29", "19-new-idea-2026-10-26"
    make(root, old, _record(old, migration=_MIGRATION), "report.md")
    make(root, new, _record(new), "report.md")
    findings = run(root)
    assert codes(findings, new) == {"number-shared": "error"}
    assert codes(findings, old) == {"number-shared": "warning"}


def _report(folder: Path, line: str) -> None:
    (folder / "report.md").write_text(
        f"# Experiment\n\n- **Folder**: `x`\n{line}\n\n## Answer\n\n- **Status**: IGNORED\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "line",
    [
        "- **Status**: FAIL — gate G2 missed",
        "- **Status:** FAIL (gates G1 to G5)",
        "**Status**: FAIL",
        "**Status:** FAIL  ",
    ],
)
def test_report_status_differs_on_new_record_is_a_warning(root: Path, line: str) -> None:
    folder = make(root, _GOOD, _record(_GOOD))
    _report(folder, line)
    findings = run(root)
    assert codes(findings, _GOOD) == {"report-status": "warning"}
    assert "PASS" in findings[0].message
    assert "FAIL" in findings[0].message


def test_report_status_differs_on_converted_record_is_info(root: Path) -> None:
    folder = make(root, _GOOD, _record(_GOOD, migration=_MIGRATION))
    _report(folder, "- **Status**: COMPLETE (measurement)")
    assert codes(run(root), _GOOD) == {"report-status": "info"}


def test_matching_or_absent_report_status_gives_no_finding(root: Path) -> None:
    folder = make(root, _GOOD, _record(_GOOD))
    _report(folder, "- **Status**: PASS — all gates")
    assert run(root) == ()
    _report(folder, "- **Date run**: 2026-05-12")
    assert run(root) == ()


def test_status_after_the_header_block_is_ignored(root: Path) -> None:
    folder = make(root, _GOOD, _record(_GOOD))
    _report(folder, "")
    assert run(root) == ()


def test_plan_changed_after_a_run_is_a_warning(root: Path) -> None:
    name = "2-std-2026-05-12"
    folder = make(root, name, _record(name, size="Standard"), "protocol.md", "report.md")
    (folder / "plan.json").write_text('{"v": 1}\n', encoding="utf-8")
    append_run_record(folder, git_commit=_COMMIT, git_dirty=False, command="run")
    assert run(root) == ()
    (folder / "plan.json").write_text('{"v": 2}\n', encoding="utf-8")
    findings = run(root)
    assert codes(findings, name) == {"plan-changed": "warning"}


def test_unreadable_run_records_is_a_warning(root: Path) -> None:
    folder = make(root, _GOOD, _record(_GOOD), "report.md")
    (folder / "output").mkdir()
    (folder / "output" / "run-records.jsonl").write_text("{bad\n", encoding="utf-8")
    assert codes(run(root), _GOOD) == {"run-records-invalid": "warning"}


@pytest.mark.parametrize(
    ("size", "files", "missing"),
    [
        ("Quick", (), ["report.md"]),
        ("Standard", ("report.md",), ["plan.json", "protocol.md"]),
        ("Confirmatory", ("plan.json", "protocol.md"), ["report.md"]),
    ],
)
def test_missing_files_for_size(
    root: Path, size: str, files: tuple[str, ...], missing: list[str]
) -> None:
    make(root, _GOOD, _record(_GOOD, size=size), *files)
    findings = run(root)
    assert codes(findings, _GOOD) == {"files-missing": "warning"}
    for file in missing:
        assert file in findings[0].message


def test_missing_files_on_converted_record_is_info(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD, size="Standard", migration=_MIGRATION), "report.md")
    assert codes(run(root), _GOOD) == {"files-missing": "info"}


def test_converted_record_without_size_or_category_is_info(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD, size=None, category=None, migration=_MIGRATION), "report.md")
    assert codes(run(root), _GOOD) == {"size-missing": "info", "category-missing": "info"}


def test_stale_index_is_an_error(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    sync_index(root)
    make(root, "2-later-2026-05-13", _record("2-later-2026-05-13"), "report.md")
    findings = check_experiments(root)
    assert codes(findings) == {"index-stale": "error"}
    assert findings[0].folder == ""


def test_index_without_markers_is_an_error(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    (root / "EXP_README.md").write_text("# Experiments\n", encoding="utf-8")
    findings = check_experiments(root)
    assert codes(findings) == {"index-markers": "error"}
    assert INDEX_START in findings[0].message


def test_missing_readme_is_a_warning(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    assert codes(check_experiments(root)) == {"index-missing": "warning"}


def _reserve(root: Path, *numbers: str) -> None:
    entries = [{"number": n, "reason": "planned", "ref": "x"} for n in numbers]
    (root / "reserved.json").write_text(
        json.dumps({"format": "omrs-experiment-reservations/1", "reservations": entries}),
        encoding="utf-8",
    )


def test_reserved_number_with_a_folder_is_info(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    _reserve(root, "1", "35")
    findings = run(root)
    assert codes(findings) == {"reserved-has-folder": "info"}
    assert findings[0].folder == _GOOD


def test_reservation_in_the_index_is_checked(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    sync_index(root)
    _reserve(root, "35")
    assert codes(check_experiments(root)) == {"index-stale": "error"}


def test_invalid_reserved_file_is_an_error(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    sync_index(root)
    (root / "reserved.json").write_text('{"format": "omrs-experiment-reservations/1", "x": 1}')
    findings = check_experiments(root)
    assert codes(findings) == {"reserved-invalid": "error"}
    assert "x" in findings[0].message


def test_findings_are_ordered_and_have_stable_codes(root: Path) -> None:
    make(root, "2-bare-2026-05-12")
    make(root, "10-bare-2026-05-12")
    findings = check_experiments(root)
    assert [f.folder for f in findings] == ["", "2-bare-2026-05-12", "10-bare-2026-05-12"]


def test_has_failures_respects_strict() -> None:
    warning = Finding(severity="warning", code="x", folder="", message="m")
    info = Finding(severity="info", code="x", folder="", message="m")
    error = Finding(severity="error", code="x", folder="", message="m")
    assert not has_failures((info, warning), strict=False)
    assert has_failures((info, warning), strict=True)
    assert not has_failures((info,), strict=True)
    assert has_failures((error,), strict=False)


def _tree_hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        key = str(path.relative_to(root))
        if path.is_dir():
            result[key] = "dir"
        else:
            result[key] = hashlib.sha256(path.read_bytes()).hexdigest() + str(
                path.stat().st_mtime_ns
            )
    return result


def test_check_leaves_every_file_unchanged(root: Path) -> None:
    make(root, _GOOD, _record(_GOOD), "report.md")
    name = "2-std-2026-05-12"
    folder = make(root, name, _record(name, size="Standard", migration=_MIGRATION), "report.md")
    (folder / "plan.json").write_text('{"v": 1}\n', encoding="utf-8")
    append_run_record(folder, git_commit=_COMMIT, git_dirty=False, command="run")
    (folder / "plan.json").write_text('{"v": 2}\n', encoding="utf-8")
    nested = folder / "output" / "index" / "deep"
    nested.mkdir(parents=True)
    (nested / "data.bin").write_bytes(b"\1" * 64)
    make(root, "3-bare-2026-05-12")
    _reserve(root, "35")
    (root / "EXP_README.md").write_text(f"# E\n{INDEX_START}\nold\n{INDEX_END}\n", encoding="utf-8")
    before = _tree_hashes(root)
    assert check_experiments(root)
    assert _tree_hashes(root) == before


def test_non_utf8_run_records_is_a_warning(root: Path) -> None:
    folder = make(root, _GOOD, _record(_GOOD), "report.md")
    (folder / "output").mkdir()
    (folder / "output" / "run-records.jsonl").write_bytes(b"\xff\xfe\n")
    assert codes(run(root), _GOOD) == {"run-records-invalid": "warning"}


def test_superseding_target_must_be_an_experiment_folder(root: Path) -> None:
    (root / "example").mkdir()
    name = "2-old-2026-05-12"
    make(root, name, _record(name, status="SUPERSEDED", superseded_by="example"), "report.md")
    findings = run(root)
    assert codes(findings, name) == {"superseded-target-missing": "error"}
    assert "example" in findings[0].message


def test_superseding_target_must_not_be_the_folder_itself(root: Path) -> None:
    name = "2-old-2026-05-12"
    make(root, name, _record(name, status="SUPERSEDED", superseded_by=name), "report.md")
    findings = run(root)
    assert codes(findings, name) == {"superseded-target-missing": "error"}
    assert "its own folder" in findings[0].message
