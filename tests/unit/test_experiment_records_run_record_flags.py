"""Optional ``prefreeze``, ``smoke`` and ``preregistration_sha256`` keys of a run record.

Experiment 35 task 5.7 (design D39): a pre-freeze run's line carries
``prefreeze: true``, a ``--qids`` smoke run's line carries ``smoke: true``, and
the line holds the SHA-256 of ``preregistration.md``. The keys are optional, so
the run records of other experiments stay valid, and a main-run line leaves the
two flags out.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omrs.core.experiment_records.record import RecordError
from omrs.core.experiment_records.run_record import (
    RUN_RECORDS_FILE,
    append_run_record,
    read_run_records,
)

_COMMIT = "9bf671b3" + "0" * 32
_PREREG = "ab" * 32
_NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


def _write(folder: Path, line: dict[str, object]) -> None:
    path = folder / "output" / RUN_RECORDS_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")


def _line(**extra: object) -> dict[str, object]:
    return {
        "format": "omrs-run-record/1",
        "started_at": "2026-11-17T09:00:00Z",
        "git_commit": _COMMIT,
        "git_dirty": True,
        "plan_sha256": "",
        "command": "run",
        **extra,
    }


def test_line_with_the_three_keys_loads(tmp_path: Path) -> None:
    _write(tmp_path, _line(prefreeze=True, smoke=True, preregistration_sha256=_PREREG))
    (record,) = read_run_records(tmp_path)
    assert record.prefreeze is True
    assert record.smoke is True
    assert record.preregistration_sha256 == _PREREG


def test_line_without_the_keys_reads_as_a_main_run(tmp_path: Path) -> None:
    _write(tmp_path, _line())
    (record,) = read_run_records(tmp_path)
    assert record.prefreeze is False
    assert record.smoke is False
    assert record.preregistration_sha256 is None


def test_bad_preregistration_hash_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, _line(preregistration_sha256="not-a-hash"))
    with pytest.raises(RecordError, match="preregistration_sha256"):
        read_run_records(tmp_path)


def test_append_writes_the_flags_and_the_hash(tmp_path: Path) -> None:
    record = append_run_record(
        tmp_path,
        git_commit=_COMMIT,
        git_dirty=True,
        command="run --prefreeze",
        now=_NOW,
        prefreeze=True,
        smoke=True,
        preregistration_sha256=_PREREG,
    )
    assert (record.prefreeze, record.smoke) == (True, True)
    text = (tmp_path / "output" / RUN_RECORDS_FILE).read_text(encoding="utf-8")
    line = json.loads(text)
    assert line["prefreeze"] is True
    assert line["smoke"] is True
    assert line["preregistration_sha256"] == _PREREG


def test_main_run_line_leaves_the_flags_out(tmp_path: Path) -> None:
    append_run_record(
        tmp_path,
        git_commit=_COMMIT,
        git_dirty=False,
        command="run",
        now=_NOW,
        preregistration_sha256=_PREREG,
    )
    text = (tmp_path / "output" / RUN_RECORDS_FILE).read_text(encoding="utf-8")
    line = json.loads(text)
    assert "prefreeze" not in line
    assert "smoke" not in line
    assert line["preregistration_sha256"] == _PREREG


def test_line_of_another_experiment_keeps_its_shape(tmp_path: Path) -> None:
    append_run_record(tmp_path, git_commit=_COMMIT, git_dirty=False, command="run", now=_NOW)
    text = (tmp_path / "output" / RUN_RECORDS_FILE).read_text(encoding="utf-8")
    assert set(json.loads(text)) == {
        "format",
        "started_at",
        "git_commit",
        "git_dirty",
        "plan_sha256",
        "command",
    }
