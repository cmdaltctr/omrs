"""Run records in ``output/run-records.jsonl`` (experiment-format-v1, task 3.4, D8)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from omrs.core.experiment_records.record import RecordError, UnsupportedFormatError
from omrs.core.experiment_records.run_record import (
    RUN_RECORD_FORMAT,
    RUN_RECORDS_FILE,
    RunRecord,
    append_run_record,
    plan_sha256,
    read_run_records,
)

_COMMIT = "9bf671b3" + "0" * 32


def _append(folder: Path, **kwargs: object) -> RunRecord:
    options: dict[str, object] = {
        "git_commit": _COMMIT,
        "git_dirty": False,
        "command": "uv run python run_eval.py",
    }
    options.update(kwargs)
    return append_run_record(folder, **options)  # type: ignore[arg-type]


def test_line_declares_format_and_utc_time(tmp_path: Path) -> None:
    _append(tmp_path)
    path = tmp_path / "output" / RUN_RECORDS_FILE
    (line,) = path.read_text(encoding="utf-8").splitlines()
    data = json.loads(line)
    assert data["format"] == RUN_RECORD_FORMAT == "omrs-run-record/1"
    assert data["started_at"].endswith("Z")
    started = datetime.fromisoformat(data["started_at"])
    assert started.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - started) < timedelta(minutes=1)
    assert data["git_commit"] == _COMMIT
    assert data["git_dirty"] is False
    assert data["command"] == "uv run python run_eval.py"


def test_second_append_keeps_first_line_byte_identical(tmp_path: Path) -> None:
    _append(tmp_path)
    path = tmp_path / "output" / RUN_RECORDS_FILE
    first = path.read_bytes()
    _append(tmp_path, git_dirty=True, command="resume")
    after = path.read_bytes()
    assert after.startswith(first)
    assert len(after.splitlines()) == 2
    assert json.loads(after.splitlines()[1])["git_dirty"] is True


def test_empty_plan_hash_without_plan(tmp_path: Path) -> None:
    record = _append(tmp_path)
    assert record.plan_sha256 == ""
    assert plan_sha256(tmp_path) == ""


def test_plan_hash_is_the_file_sha256(tmp_path: Path) -> None:
    (tmp_path / "plan.json").write_bytes(b'{"hypothesis": "x"}\n')
    record = _append(tmp_path)
    expected = hashlib.sha256(b'{"hypothesis": "x"}\n').hexdigest()
    assert record.plan_sha256 == expected == plan_sha256(tmp_path)


def test_given_start_time_is_converted_to_utc(tmp_path: Path) -> None:
    local = datetime(2026, 10, 25, 14, 0, tzinfo=timezone(timedelta(hours=1)))
    record = _append(tmp_path, now=local)
    assert record.started_at == datetime(2026, 10, 25, 13, 0, tzinfo=UTC)


def test_naive_start_time_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="time zone"):
        _append(tmp_path, now=datetime(2026, 10, 25, 14, 0))  # noqa: DTZ001


def test_read_returns_records_in_order(tmp_path: Path) -> None:
    _append(tmp_path, command="first")
    _append(tmp_path, command="second")
    assert [r.command for r in read_run_records(tmp_path)] == ["first", "second"]


def test_read_without_file_is_empty(tmp_path: Path) -> None:
    assert read_run_records(tmp_path) == ()


def test_read_names_a_bad_line(tmp_path: Path) -> None:
    _append(tmp_path)
    path = tmp_path / "output" / RUN_RECORDS_FILE
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"format": "omrs-run-record/1", "extra": 1}\n')
    with pytest.raises(RecordError, match="line 2"):
        read_run_records(tmp_path)


def test_read_refuses_newer_format(tmp_path: Path) -> None:
    path = tmp_path / "output" / RUN_RECORDS_FILE
    path.parent.mkdir()
    path.write_text('{"format": "omrs-run-record/2"}\n', encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        read_run_records(tmp_path)


def test_record_refuses_bad_plan_hash() -> None:
    with pytest.raises(ValueError):
        RunRecord(
            format="omrs-run-record/1",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            git_commit=_COMMIT,
            git_dirty=False,
            plan_sha256="not-a-hash",
            command="x",
        )


def test_non_utf8_file_is_a_record_error(tmp_path: Path) -> None:
    path = tmp_path / "output" / RUN_RECORDS_FILE
    path.parent.mkdir()
    path.write_bytes(b'{"format": "omrs-run-record/1"}\xff\n')
    with pytest.raises(RecordError, match="UTF-8"):
        read_run_records(tmp_path)


@pytest.mark.parametrize("separator", [" ", " ", "\x85"])
def test_unicode_line_separator_in_command_round_trips(tmp_path: Path, separator: str) -> None:
    command = f"run{separator}eval"
    _append(tmp_path, command=command)
    _append(tmp_path, command="second")
    assert [r.command for r in read_run_records(tmp_path)] == [command, "second"]
