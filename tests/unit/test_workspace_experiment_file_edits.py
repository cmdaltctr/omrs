"""Saving protocol and report files (edit-experiment-files-in-library, task 4.1, D1, D4, D5)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.edit_log import EDIT_LOG_FILE, read_edits
from omrs.core.experiment_records.record import Category, Size
from omrs.core.experiment_records.scaffold import create_experiment
from omrs.core.workspace import experiment_file_edits as edits
from omrs.core.workspace.experiment_pages import (
    ExperimentNotFoundError,
    ExperimentRefusedError,
)

FOLDER = "1-first-run-2026-01-01"
TOOL = "omrs web 0.0.0"
NOW = datetime(2026, 10, 26, 14, 5, 7, 123456, tzinfo=UTC)
MIB = 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def experiments(tmp_path: Path) -> Path:
    root = tmp_path / "experiments"
    root.mkdir()
    create_experiment(
        root,
        slug="first-run",
        title="First run",
        category=Category.RETRIEVAL,
        size=Size.STANDARD,
        day=date(2026, 1, 1),
    )
    folder = root / FOLDER
    (folder / "protocol.md").write_bytes(b"# Protocol\n\nOld text.\n")
    (folder / "report.md").write_bytes(b"# Report\n")
    return root.resolve()


@pytest.fixture
def folder(experiments: Path) -> Path:
    return experiments / FOLDER


def save(experiments: Path, name: str, text: str, base: str | None = None, **kw: Any) -> dict:
    path = experiments / FOLDER / name
    revision = base if base is not None else sha(path.read_bytes())
    return edits.save_file(experiments, FOLDER, name, text, revision, TOOL, now=NOW, **kw)


def set_record(folder: Path, **changes: Any) -> None:
    path = folder / "experiment.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith("."))


# --- which files are editable -------------------------------------------------


def test_protocol_and_report_are_editable_and_results_only_without_report(folder: Path) -> None:
    assert edits.editable_names(folder) == {"protocol.md", "report.md"}
    (folder / "report.md").unlink()
    assert edits.editable_names(folder) == {"protocol.md", "results.md"}


@pytest.mark.parametrize("name", ["plan.json", "analysis.py", "../x.md", ".hidden.md", "notes.md"])
def test_refused_names_need_no_file_access(tmp_path: Path, name: str) -> None:
    missing = tmp_path / "does-not-exist"  # any disk access would raise another error
    with pytest.raises(ExperimentRefusedError):
        edits.save_file(missing, FOLDER, name, "x", "0" * 64, TOOL)


def test_results_next_to_report_is_refused(experiments: Path, folder: Path) -> None:
    (folder / "results.md").write_bytes(b"old\n")
    with pytest.raises(ExperimentRefusedError):
        save(experiments, "results.md", "new\n")
    assert (folder / "results.md").read_bytes() == b"old\n"


def test_results_without_report_saves(experiments: Path, folder: Path) -> None:
    (folder / "report.md").unlink()
    (folder / "results.md").write_bytes(b"old\n")
    assert save(experiments, "results.md", "new\n")["changed"] is True
    assert (folder / "results.md").read_bytes() == b"new\n"


def test_missing_file_is_refused_and_not_created(experiments: Path, folder: Path) -> None:
    (folder / "protocol.md").unlink()
    with pytest.raises(ExperimentRefusedError):
        save(experiments, "protocol.md", "new\n", base="0" * 64)
    assert not (folder / "protocol.md").exists()
    assert not (folder / EDIT_LOG_FILE).exists()


def test_unknown_folder_is_not_found(experiments: Path) -> None:
    with pytest.raises(ExperimentNotFoundError):
        edits.save_file(experiments, "9-nope-2026-01-01", "report.md", "x", "0" * 64, TOOL)


def test_link_is_not_editable_and_not_saved(
    experiments: Path, folder: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside\n")
    (folder / "report.md").unlink()
    (folder / "report.md").symlink_to(outside)
    assert not edits.is_editable(folder, "report.md", b"outside\n", 8)
    with pytest.raises(ExperimentRefusedError):
        save(experiments, "report.md", "new\n", base=sha(b"outside\n"))
    assert outside.read_bytes() == b"outside\n"


def test_large_or_non_utf8_file_is_not_editable(folder: Path) -> None:
    assert edits.is_editable(folder, "report.md", b"ok", 2)
    assert not edits.is_editable(folder, "report.md", b"a" * (MIB + 1), MIB + 1)
    assert not edits.is_editable(folder, "report.md", b"ok \xff", 4)
    assert not edits.is_editable(folder, "plan.json", b"{}", 2)


def test_non_utf8_file_is_refused_on_save(experiments: Path, folder: Path) -> None:
    (folder / "report.md").write_bytes(b"bad \xff\n")
    with pytest.raises(ExperimentRefusedError):
        save(experiments, "report.md", "new\n")
    assert (folder / "report.md").read_bytes() == b"bad \xff\n"


# --- revision and text rules --------------------------------------------------


def test_stale_revision_is_changed_on_disk(experiments: Path, folder: Path) -> None:
    with pytest.raises(edits.ExperimentEditConflictError) as caught:
        save(experiments, "protocol.md", "new\n", base=sha(b"something else"))
    assert caught.value.reason == "changed_on_disk"
    assert (folder / "protocol.md").read_bytes() == b"# Protocol\n\nOld text.\n"
    assert not (folder / EDIT_LOG_FILE).exists()


def test_equal_text_changes_nothing(experiments: Path, folder: Path) -> None:
    answer = save(experiments, "protocol.md", "# Protocol\n\nOld text.\n")
    assert answer["changed"] is False
    assert answer["revision"] == sha(b"# Protocol\n\nOld text.\n")
    assert answer["last_edited"] is None
    assert not (folder / EDIT_LOG_FILE).exists()


def test_crlf_file_keeps_crlf(experiments: Path, folder: Path) -> None:
    (folder / "protocol.md").write_bytes(b"# P\r\n\r\nOld.\r\n")
    save(experiments, "protocol.md", "# P\n\nNew.\n")
    assert (folder / "protocol.md").read_bytes() == b"# P\r\n\r\nNew.\r\n"


def test_lf_file_stays_lf(experiments: Path, folder: Path) -> None:
    save(experiments, "protocol.md", "# P\r\nNew.\n")
    assert (folder / "protocol.md").read_bytes() == b"# P\nNew.\n"


def test_byte_order_mark_is_kept(experiments: Path, folder: Path) -> None:
    (folder / "protocol.md").write_bytes(b"\xef\xbb\xbf# P\n")
    save(experiments, "protocol.md", "﻿# P\nNew.\n")
    assert (folder / "protocol.md").read_bytes() == b"\xef\xbb\xbf# P\nNew.\n"


@pytest.mark.parametrize("text", ["a" * (MIB + 1), "nul \x00 here"])
def test_large_or_nul_text_is_refused(experiments: Path, folder: Path, text: str) -> None:
    with pytest.raises(ExperimentRefusedError):
        save(experiments, "protocol.md", text)
    assert (folder / "protocol.md").read_bytes() == b"# Protocol\n\nOld text.\n"


# --- a successful save --------------------------------------------------------


def test_save_replaces_the_file_and_logs_one_line(experiments: Path, folder: Path) -> None:
    record_before = (folder / "experiment.json").read_bytes()
    mode = 0o640
    os.chmod(folder / "protocol.md", mode)
    answer = save(experiments, "protocol.md", "# Protocol\n\nNew text.\n")
    data = (folder / "protocol.md").read_bytes()
    assert data == b"# Protocol\n\nNew text.\n"
    assert (folder / "protocol.md").stat().st_mode & 0o777 == mode
    assert answer == {
        "name": "protocol.md",
        "revision": sha(data),
        "size": len(data),
        "changed": True,
        "last_edited": {
            "edited_at": "2026-10-26T14:05:07Z",
            "status": "PLANNED",
            "converted": False,
        },
    }
    (line,) = read_edits(folder)
    assert line.file == "protocol.md"
    assert line.after_sha256 == sha(data)
    assert line.before_sha256 == sha(b"# Protocol\n\nOld text.\n")
    assert (line.before_size, line.after_size) == (22, len(data))
    assert line.tool == TOOL
    assert leftovers(folder) == []
    assert (folder / "experiment.json").read_bytes() == record_before


def test_second_save_appends_a_second_line(experiments: Path, folder: Path) -> None:
    save(experiments, "protocol.md", "one\n")
    first = (folder / EDIT_LOG_FILE).read_bytes()
    save(experiments, "report.md", "two\n")
    after = (folder / EDIT_LOG_FILE).read_bytes()
    assert after.startswith(first)
    assert [e.file for e in read_edits(folder)] == ["protocol.md", "report.md"]


def test_log_line_takes_status_and_converted_from_the_record(
    experiments: Path, folder: Path
) -> None:
    migration = {"from_status": "PASS", "source": "EXP_README.md", "date": "2026-10-25"}
    set_record(folder, status="PASS", finding="Found.", migration=migration)
    save(experiments, "report.md", "new\n")
    (line,) = read_edits(folder)
    assert (line.status.value, line.converted) == ("PASS", True)


def test_last_edited_view(experiments: Path, folder: Path) -> None:
    assert edits.last_edited_view(folder, "protocol.md") is None
    save(experiments, "protocol.md", "new\n")
    assert edits.last_edited_view(folder, "protocol.md") == {
        "edited_at": "2026-10-26T14:05:07Z",
        "status": "PLANNED",
        "converted": False,
    }
    assert edits.last_edited_view(folder, "report.md") is None


# --- failures -------------------------------------------------------------------


def test_edit_log_link_is_refused_before_any_write(
    experiments: Path, folder: Path, tmp_path: Path
) -> None:
    target = tmp_path / "elsewhere.jsonl"
    target.write_bytes(b"")
    (folder / EDIT_LOG_FILE).symlink_to(target)
    with pytest.raises(edits.ExperimentEditConflictError) as caught:
        save(experiments, "protocol.md", "new\n")
    assert caught.value.reason == "edit_log_unusable"
    assert (folder / "protocol.md").read_bytes() == b"# Protocol\n\nOld text.\n"
    assert target.read_bytes() == b""


def test_failing_rename_keeps_the_old_text(
    experiments: Path, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("no rename")

    monkeypatch.setattr(edits.os, "replace", broken)
    with pytest.raises(edits.ExperimentEditFailedError) as caught:
        save(experiments, "protocol.md", "new\n")
    assert str(caught.value) == edits.WRITE_FAILED
    assert (folder / "protocol.md").read_bytes() == b"# Protocol\n\nOld text.\n"
    assert leftovers(folder) == []
    assert not (folder / EDIT_LOG_FILE).exists()


def test_failing_log_append_restores_the_old_text(
    experiments: Path, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(edits, "append_edit", broken)
    with pytest.raises(edits.ExperimentEditFailedError) as caught:
        save(experiments, "protocol.md", "new\n")
    assert str(caught.value) == edits.NOT_SAVED
    assert "/" not in str(caught.value)
    assert (folder / "protocol.md").read_bytes() == b"# Protocol\n\nOld text.\n"
    assert leftovers(folder) == []


def test_failing_restore_says_saved_but_not_recorded(
    experiments: Path, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace
    calls = {"n": 0}

    def replace_once(*args: Any, **kwargs: Any) -> None:
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("no restore")
        real_replace(*args, **kwargs)

    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(edits.os, "replace", replace_once)
    monkeypatch.setattr(edits, "append_edit", broken)
    with pytest.raises(edits.ExperimentEditFailedError) as caught:
        save(experiments, "protocol.md", "new\n")
    assert str(caught.value) == edits.SAVED_NOT_RECORDED
    assert (folder / "protocol.md").read_bytes() == b"new\n"
    assert leftovers(folder) == []
