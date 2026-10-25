"""Experiment folder detection (experiment-format-v1, task 3.2, spec "detected").

A direct subfolder is an experiment when it holds ``experiment.json`` or
when its name follows ``<number>-<slug>-<YYYY-MM-DD>``. Only the top level
of ``output/`` is listed; nothing inside it is opened.
"""

from __future__ import annotations

import builtins
import io
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.scan import scan_experiments


def record(number: str, day: str, **overrides: Any) -> dict[str, Any]:
    """Return a valid record dict for tests."""
    data: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": number,
        "title": f"Experiment {number or 'unnumbered'}",
        "date": day,
        "category": "retrieval",
        "size": "Quick",
        "status": "PLANNED",
        "superseded_by": None,
        "finding": "Planned.",
    }
    data.update(overrides)
    return data


def make(root: Path, name: str, data: dict[str, Any] | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if data is not None:
        (folder / "experiment.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path


def test_shared_folders_are_ignored(root: Path) -> None:
    for name in ("_lib", "ARCHIVED", "example", ".git", "notes-2026-01-01"):
        make(root, name)
    (root / "EXP_README.md").write_text("# Experiments\n", encoding="utf-8")
    (root / "22-loose-file-2026-09-07").write_text("not a folder", encoding="utf-8")
    assert scan_experiments(root) == ()


def test_folder_with_record_is_detected(root: Path) -> None:
    make(root, "22-raw-query-2026-09-07", record("22", "2026-09-07"))
    (found,) = scan_experiments(root)
    assert found.name == "22-raw-query-2026-09-07"
    assert found.record is not None
    assert found.record.number == "22"
    assert found.record_error is None
    assert found.number == "22"


def test_folder_matched_by_name_only_is_detected_without_record(root: Path) -> None:
    make(root, "6c-markdown-quickwins-2026-05-28")
    (found,) = scan_experiments(root)
    assert found.record is None
    assert found.has_record_file is False
    assert found.record_error is not None
    assert "experiment.json" in found.record_error
    assert found.number == "6c"


def test_unnumbered_folder_needs_a_record(root: Path) -> None:
    make(root, "leiden-vs-louvain-2026-08-14", record("", "2026-08-14"))
    make(root, "other-idea-2026-08-15")
    (found,) = scan_experiments(root)
    assert found.name == "leiden-vs-louvain-2026-08-14"
    assert found.number == ""


def test_folder_with_record_but_odd_name_is_detected(root: Path) -> None:
    make(root, "Odd Name", record("7", "2026-01-01"))
    (found,) = scan_experiments(root)
    assert found.parsed is None
    assert found.number == "7"


def test_invalid_record_is_reported_not_raised(root: Path) -> None:
    make(root, "22-raw-query-2026-09-07", record("22", "2026-09-07", owner="x"))
    (found,) = scan_experiments(root)
    assert found.record is None
    assert found.has_record_file is True
    assert found.record_error is not None
    assert "owner" in found.record_error


def test_two_folders_with_the_same_number_stay_separate(root: Path) -> None:
    migration = {"from_status": "PASS", "source": "EXP_README.md", "date": "2026-10-25"}
    make(root, "19-native-fts-2026-08-29", record("19", "2026-08-29", migration=migration))
    make(root, "19-lancedb-lifecycle-2026-08-21", record("19", "2026-08-21", migration=migration))
    found = scan_experiments(root)
    assert [item.name for item in found] == [
        "19-lancedb-lifecycle-2026-08-21",
        "19-native-fts-2026-08-29",
    ]
    assert all(item.is_converted for item in found)


def test_folders_come_back_in_natural_order(root: Path) -> None:
    for name in (
        "10b-x-2026-01-01",
        "10.1-x-2026-01-01",
        "10-x-2026-01-01",
        "5b-x-2026-01-01",
        "5-x-2026-01-01",
        "6-x-2026-01-01",
    ):
        make(root, name)
    make(root, "leiden-vs-louvain-2026-08-14", record("", "2026-08-14"))
    assert [item.name for item in scan_experiments(root)] == [
        "5-x-2026-01-01",
        "5b-x-2026-01-01",
        "6-x-2026-01-01",
        "10-x-2026-01-01",
        "10.1-x-2026-01-01",
        "10b-x-2026-01-01",
        "leiden-vs-louvain-2026-08-14",
    ]


@pytest.fixture
def opened_paths(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every path opened through ``open``."""
    seen: list[str] = []
    real_open = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(os.fspath(file) if isinstance(file, (str, os.PathLike)) else repr(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    yield seen


def test_output_lists_only_top_level_names(root: Path, opened_paths: list[str]) -> None:
    folder = make(root, "22-raw-query-2026-09-07", record("22", "2026-09-07"))
    nested = folder / "output" / "chroma_index" / "deep"
    nested.mkdir(parents=True)
    (nested / "segment.bin").write_bytes(b"\0" * 1024)
    (folder / "output" / "results.json").write_text("{}", encoding="utf-8")
    locked = folder / "output" / "chroma_index"
    locked.chmod(0)
    opened_paths.clear()
    try:
        (found,) = scan_experiments(root)
    finally:
        locked.chmod(0o755)
    assert found.output_names == ("chroma_index", "results.json")
    output = str(folder / "output")
    assert not [path for path in opened_paths if path.startswith(output)]


def test_no_output_folder_gives_no_names(root: Path) -> None:
    make(root, "22-raw-query-2026-09-07", record("22", "2026-09-07"))
    assert scan_experiments(root)[0].output_names == ()


def test_missing_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError, match="missing"):
        scan_experiments(tmp_path / "missing")
