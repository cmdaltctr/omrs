"""Edit records in ``edits.jsonl`` (edit-experiment-files-in-library, task 2.1, D3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from omrs.core.experiment_records.edit_log import (
    EDIT_LOG_FILE,
    EDIT_RECORD_FORMAT,
    EditRecord,
    append_edit,
    last_edit,
    read_edits,
)
from omrs.core.experiment_records.record import RecordError, UnsupportedFormatError

_A = "a" * 64
_B = "b" * 64


def _record(**overrides: object) -> EditRecord:
    data: dict[str, object] = {
        "format": EDIT_RECORD_FORMAT,
        "file": "protocol.md",
        "edited_at": datetime(2026, 10, 26, 14, 5, 0, tzinfo=UTC),
        "before_sha256": _A,
        "after_sha256": _B,
        "before_size": 10,
        "after_size": 12,
        "status": "PASS",
        "converted": True,
        "tool": "omrs web 3.4.0",
    }
    data.update(overrides)
    return EditRecord.model_validate(data)


def _line(**overrides: object) -> str:
    return json.dumps(_record().model_dump(mode="json") | overrides)


def test_valid_line_loads_with_key_order_and_utc_time(tmp_path: Path) -> None:
    append_edit(tmp_path, _record())
    (line,) = (tmp_path / EDIT_LOG_FILE).read_text(encoding="utf-8").splitlines()
    data = json.loads(line)
    assert list(data) == [
        "format",
        "file",
        "edited_at",
        "before_sha256",
        "after_sha256",
        "before_size",
        "after_size",
        "status",
        "converted",
        "tool",
    ]
    assert data["format"] == EDIT_RECORD_FORMAT == "omrs-edit-record/1"
    assert data["edited_at"] == "2026-10-26T14:05:00Z"
    assert read_edits(tmp_path) == (_record(),)


def test_unknown_key_fails_and_names_the_key(tmp_path: Path) -> None:
    (tmp_path / EDIT_LOG_FILE).write_text(_line(author="someone") + "\n", encoding="utf-8")
    with pytest.raises(RecordError, match="author"):
        read_edits(tmp_path)


def test_unknown_format_fails_and_names_the_version(tmp_path: Path) -> None:
    (tmp_path / EDIT_LOG_FILE).write_text(
        _line(format="omrs-edit-record/2") + "\n", encoding="utf-8"
    )
    with pytest.raises(UnsupportedFormatError, match="omrs-edit-record/2"):
        read_edits(tmp_path)


@pytest.mark.parametrize("name", ["sub/protocol.md", "..\\report.md", "..", ""])
def test_file_with_a_path_part_fails(name: str) -> None:
    with pytest.raises(ValueError):
        _record(file=name)


def test_time_without_utc_fails() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _record(edited_at=datetime(2026, 10, 26, 14, 5, tzinfo=timezone(timedelta(hours=1))))
    with pytest.raises(ValueError, match="UTC"):
        _record(edited_at=datetime(2026, 10, 26, 14, 5))  # noqa: DTZ001


def test_tool_must_be_one_line() -> None:
    with pytest.raises(ValueError):
        _record(tool="omrs\nweb")


def test_append_creates_the_file_and_keeps_the_first_line(tmp_path: Path) -> None:
    path = tmp_path / EDIT_LOG_FILE
    append_edit(tmp_path, _record())
    first = path.read_bytes()
    append_edit(tmp_path, _record(file="report.md"))
    after = path.read_bytes()
    assert after.startswith(first)
    assert len(after.splitlines()) == 2


def test_append_adds_a_newline_first_when_missing(tmp_path: Path) -> None:
    path = tmp_path / EDIT_LOG_FILE
    path.write_text(_line(), encoding="utf-8")
    append_edit(tmp_path, _record(file="report.md"))
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[-1] == ""
    assert [json.loads(line)["file"] for line in lines[:-1]] == ["protocol.md", "report.md"]


def test_append_refuses_a_link(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("", encoding="utf-8")
    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / EDIT_LOG_FILE).symlink_to(target)
    with pytest.raises(OSError):
        append_edit(folder, _record())
    assert target.read_text(encoding="utf-8") == ""


def test_read_refuses_a_link(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.jsonl"
    target.write_text(_line() + "\n", encoding="utf-8")
    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / EDIT_LOG_FILE).symlink_to(target)
    with pytest.raises(RecordError, match="link"):
        read_edits(folder)


def test_read_without_file_is_empty(tmp_path: Path) -> None:
    assert read_edits(tmp_path) == ()


def test_last_edit_returns_the_newest_line_for_the_name(tmp_path: Path) -> None:
    append_edit(tmp_path, _record(edited_at=datetime(2026, 10, 1, tzinfo=UTC)))
    append_edit(tmp_path, _record(edited_at=datetime(2026, 10, 2, tzinfo=UTC)))
    append_edit(tmp_path, _record(file="report.md", edited_at=datetime(2026, 10, 3, tzinfo=UTC)))
    newest = last_edit(tmp_path, "protocol.md")
    assert newest is not None
    assert newest.edited_at == datetime(2026, 10, 2, tzinfo=UTC)
    assert last_edit(tmp_path, "results.md") is None


def test_last_edit_skips_broken_lines(tmp_path: Path) -> None:
    append_edit(tmp_path, _record())
    with (tmp_path / EDIT_LOG_FILE).open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    assert last_edit(tmp_path, "protocol.md") == _record()


def test_broken_line_is_reported_with_its_number(tmp_path: Path) -> None:
    append_edit(tmp_path, _record())
    append_edit(tmp_path, _record())
    with (tmp_path / EDIT_LOG_FILE).open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    with pytest.raises(RecordError, match="line 3"):
        read_edits(tmp_path)
