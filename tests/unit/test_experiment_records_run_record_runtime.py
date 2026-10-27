"""The optional ``runtime`` key of a run record (reproducible-experiment-runtime, task 3.3).

Old lines without the key still load. A new line with the key round-trips,
and a line without it is written without the key, so the file shape of old
runs does not change.
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
_SHA = "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"
_RUNTIME = {"build": 11671, "models": [{"file": "Qwen3-Embedding-0.6B-Q8_0.gguf", "sha256": _SHA}]}
_NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def _lines(folder: Path) -> list[dict[str, object]]:
    text = (folder / "output" / RUN_RECORDS_FILE).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_old_line_without_runtime_still_loads(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    old = {
        "format": "omrs-run-record/1",
        "started_at": "2026-10-26T09:00:00Z",
        "git_commit": _COMMIT,
        "git_dirty": False,
        "plan_sha256": "",
        "command": "uv run python run_eval.py",
    }
    (tmp_path / "output" / RUN_RECORDS_FILE).write_text(json.dumps(old) + "\n", encoding="utf-8")
    (record,) = read_run_records(tmp_path)
    assert record.runtime is None


def test_line_without_runtime_is_written_without_the_key(tmp_path: Path) -> None:
    append_run_record(tmp_path, git_commit=_COMMIT, git_dirty=False, command="x", now=_NOW)
    (line,) = _lines(tmp_path)
    assert "runtime" not in line


def test_line_with_runtime_round_trips(tmp_path: Path) -> None:
    written = append_run_record(
        tmp_path, git_commit=_COMMIT, git_dirty=False, command="x", now=_NOW, runtime=_RUNTIME
    )
    (line,) = _lines(tmp_path)
    assert line["runtime"] == _RUNTIME
    (read,) = read_run_records(tmp_path)
    assert read == written
    assert read.runtime is not None
    assert read.runtime.build == 11671
    assert read.runtime.models[0].sha256 == _SHA


@pytest.mark.parametrize(
    "runtime",
    [
        {"build": 11671},
        {"build": 11671, "models": [{"file": "a.gguf", "sha256": "abc"}]},
        {"build": "b11671", "models": []},
        {"build": 11671, "models": [], "extra": 1},
    ],
)
def test_invalid_runtime_is_refused(tmp_path: Path, runtime: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="runtime"):
        append_run_record(
            tmp_path, git_commit=_COMMIT, git_dirty=False, command="x", now=_NOW, runtime=runtime
        )
    assert not (tmp_path / "output" / RUN_RECORDS_FILE).exists()


def test_invalid_runtime_in_a_line_names_the_line(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    bad = {
        "format": "omrs-run-record/1",
        "started_at": "2026-10-26T09:00:00Z",
        "git_commit": _COMMIT,
        "git_dirty": False,
        "plan_sha256": "",
        "command": "x",
        "runtime": {"build": 1, "models": [{"file": "a.gguf"}]},
    }
    (tmp_path / "output" / RUN_RECORDS_FILE).write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(RecordError, match="line 1.*runtime"):
        read_run_records(tmp_path)


def test_line_with_unchecked_arm_round_trips(tmp_path: Path) -> None:
    runtime = {
        **_RUNTIME,
        "unchecked": [
            {
                "role": "decision",
                "runtime": "mlx",
                "version": "0.29.1",
                "file": "model.safetensors",
                "sha256": "1" * 64,
            }
        ],
    }
    written = append_run_record(
        tmp_path, git_commit=_COMMIT, git_dirty=False, command="x", now=_NOW, runtime=runtime
    )
    (line,) = _lines(tmp_path)
    assert line["runtime"] == runtime
    (read,) = read_run_records(tmp_path)
    assert read == written
    assert read.runtime is not None
    assert read.runtime.unchecked[0].runtime == "mlx"
