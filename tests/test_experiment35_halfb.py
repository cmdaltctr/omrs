"""Experiment 35 half-B guard in ``scoring35.write_scores`` (task 16.17; pre-registration 14.2).

No half-B score is written or computed before ``selection.json`` exists and
the OSF time-stamp record holds its configuration hash. Half A needs neither.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load

scoring35 = load("scoring35")

HASH = "a" * 64
OLD = "b" * 64


def _selection(out: Path, digest: str = HASH) -> None:
    (out / "selection.json").write_text(json.dumps({"configuration_hash": digest}))


def _stamp(out: Path, digest: str = HASH) -> None:
    record = {"uploaded_at": "2026-12-01T10:00:00Z", "file_sha256": "c" * 64}
    (out / "osf-timestamp.json").write_text(json.dumps({**record, "configuration_hash": digest}))


def test_half_a_needs_neither_file(tmp_path: Path) -> None:
    scoring35.write_scores(tmp_path / "a.jsonl", [{"qid": "q"}], half="A", root=tmp_path)
    assert (tmp_path / "a.jsonl").exists()


def test_half_b_refuses_with_both_files_missing_and_names_both(tmp_path: Path) -> None:
    with pytest.raises(scoring35.HalfBLocked) as caught:
        scoring35.write_scores(tmp_path / "b.jsonl", [{"qid": "q"}], half="B", root=tmp_path)
    assert "selection.json" in str(caught.value)
    assert "osf-timestamp.json" in str(caught.value)
    assert not (tmp_path / "b.jsonl").exists()


@pytest.mark.parametrize("present", ["selection", "stamp"])
def test_half_b_refuses_with_one_file_missing(tmp_path: Path, present: str) -> None:
    (_selection if present == "selection" else _stamp)(tmp_path)
    missing = "osf-timestamp.json" if present == "selection" else "selection.json"
    with pytest.raises(scoring35.HalfBLocked, match=missing):
        scoring35.write_scores(tmp_path / "b.jsonl", {"n": 1}, half="B", root=tmp_path)
    assert not (tmp_path / "b.jsonl").exists()


def test_half_b_refuses_a_stamp_of_an_earlier_selection_and_names_both_hashes(
    tmp_path: Path,
) -> None:
    _selection(tmp_path, HASH)
    _stamp(tmp_path, OLD)
    with pytest.raises(scoring35.HalfBLocked) as caught:
        scoring35.write_scores(tmp_path / "b.jsonl", {"n": 1}, half="B", root=tmp_path)
    assert HASH in str(caught.value) and OLD in str(caught.value)


def test_half_b_refuses_a_stamp_without_upload_time_or_file_hash(tmp_path: Path) -> None:
    _selection(tmp_path)
    (tmp_path / "osf-timestamp.json").write_text(json.dumps({"configuration_hash": HASH}))
    with pytest.raises(scoring35.HalfBLocked, match="uploaded_at"):
        scoring35.write_scores(tmp_path / "b.jsonl", {"n": 1}, half="B", root=tmp_path)


def test_half_b_without_a_root_refuses(tmp_path: Path) -> None:
    with pytest.raises(scoring35.HalfBLocked, match="selection.json"):
        scoring35.write_scores(tmp_path / "b.jsonl", {"n": 1}, half="B")


def test_half_b_writes_once_the_stamp_holds_the_current_hash(tmp_path: Path) -> None:
    _selection(tmp_path)
    _stamp(tmp_path)
    scoring35.require_half_b(tmp_path)
    scoring35.write_scores(tmp_path / "b.jsonl", [{"qid": "q"}], half="B", root=tmp_path)
    assert json.loads((tmp_path / "b.jsonl").read_text()) == {"qid": "q"}
