"""Experiment 35 G2 rebuild check, ``rebuild35.py`` (task 6.4; design D20; H-21)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load

rebuild35 = load("rebuild35")


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _row(qid: str, ids: list[str]) -> dict:
    return {"qid": qid, "chunks": [{"chunk_id": i, "score": 0.1} for i in ids]}


def _run(tmp_path: Path, a_rows: list[dict], b_rows: list[dict]) -> tuple[int, dict]:
    a = _write(tmp_path / "check" / "search.jsonl", a_rows)
    b = _write(tmp_path / "rebuild" / "search.jsonl", b_rows)
    out = tmp_path / "out"
    code = rebuild35.main(
        ["--a", str(a), "--b", str(b), "--out-dir", str(out), "--dataset", "bioasq"]
    )
    return code, json.loads((out / "bioasq" / "rebuild.json").read_text())


def test_same_ranked_ids_pass(tmp_path: Path) -> None:
    rows = [_row("q1", ["a", "b"]), _row("q2", ["c"])]
    code, report = _run(tmp_path, rows, rows)
    assert code == 0
    assert report["ok"] is True
    assert report["questions_compared"] == 2


def test_another_order_fails_names_the_question_and_exits_3(tmp_path: Path) -> None:
    code, report = _run(
        tmp_path,
        [_row("q1", ["a", "b"]), _row("q2", ["c"])],
        [_row("q1", ["b", "a"]), _row("q2", ["c"])],
    )
    assert code == rebuild35.EXIT_MISMATCH == 3
    assert report["ok"] is False
    assert [m["question_id"] for m in report["mismatches"]] == ["q1"]


def test_a_row_on_one_side_only_is_a_mismatch(tmp_path: Path) -> None:
    code, report = _run(tmp_path, [_row("q1", ["a"]), _row("q2", ["c"])], [_row("q1", ["a"])])
    assert code == 3
    assert report["mismatches"][0]["question_id"] == "q2"


@pytest.mark.parametrize("b_row", [_row("q2", []), {"qid": "q2", "missing": True, "error": "boom"}])
def test_failed_searches_count_as_incomplete_never_as_a_match(tmp_path: Path, b_row: dict) -> None:
    code, report = _run(tmp_path, [_row("q1", ["a"]), _row("q2", [])], [_row("q1", ["a"]), b_row])
    assert code == 3
    assert report["ok"] is False
    assert report["incomplete"] == [{"question_id": "q2", "reason": "search failed in a, b"}]
    assert report["mismatches"] == []


def test_one_failed_side_is_incomplete_and_names_the_side(tmp_path: Path) -> None:
    code, report = _run(tmp_path, [_row("q1", ["a"])], [_row("q1", [])])
    assert code == 3
    assert report["incomplete"] == [{"question_id": "q1", "reason": "search failed in b"}]


def test_reads_only_the_two_files_and_writes_only_the_report(tmp_path: Path) -> None:
    rows = [_row("q1", ["a"])]
    a = _write(tmp_path / "check" / "search.jsonl", rows)
    b = _write(tmp_path / "rebuild" / "search.jsonl", rows)
    _write(tmp_path / "check" / "other.jsonl", [{"qid": "x"}])
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    out = tmp_path / "out"
    rebuild35.main(["--a", str(a), "--b", str(b), "--out-dir", str(out), "--dataset", "bioasq"])
    after = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert after - before == {out / "bioasq" / "rebuild.json"}


def test_help_shows_the_two_inputs_and_the_output_folder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        rebuild35.main(["--help"])
    text = capsys.readouterr().out
    for option in ("--a", "--b", "--out-dir", "--dataset"):
        assert option in text
