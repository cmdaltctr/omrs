"""Experiment 35 G2 rebuild check, ``rebuild35.py`` (task 6.4; design D20; H-21)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from tests._exp35_fixtures import load

rebuild35 = load("rebuild35")
SETUP = "e4b-c1024-roff-hoff"


def _list(root: Path, side: str) -> Path:
    return root / side / "bioasq" / "search" / SETUP / "run1" / "search.jsonl"


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _row(qid: str, ids: list[str]) -> dict:
    return {"qid": qid, "chunks": [{"chunk_id": i, "score": 0.1} for i in ids]}


def _run(tmp_path: Path, a_rows: list[dict], b_rows: list[dict]) -> tuple[int, dict]:
    a = _write(_list(tmp_path, "check"), a_rows)
    b = _write(_list(tmp_path, "rebuild"), b_rows)
    out = tmp_path / "out"
    asked = len({r["qid"] for r in a_rows + b_rows})
    with mock.patch.dict(rebuild35.FROZEN, {"bioasq": asked}):  # the fixture's question count
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
    assert report["setup"] == SETUP


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
    a = _write(_list(tmp_path, "check"), rows)
    b = _write(_list(tmp_path, "rebuild"), rows)
    _write(a.parent / "other.jsonl", [{"qid": "x"}])
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    out = tmp_path / "out"
    with mock.patch.dict(rebuild35.FROZEN, {"bioasq": 1}):
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


# --- refusals (review B3): G2 never passes on nothing --------------------------------------


def _refuses(tmp_path: Path, a: Path, b: Path, *extra: str) -> str:
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as caught:
        rebuild35.main(
            ["--a", str(a), "--b", str(b), "--out-dir", str(out), "--dataset", "bioasq", *extra]
        )
    assert caught.value.code == 2
    assert not (out / "bioasq" / "rebuild.json").exists()
    return str(caught.value)


@pytest.mark.parametrize("which", ["a", "b"])
def test_refuses_a_missing_file(
    tmp_path: Path, which: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_row("q1", ["a"])]
    a, b = _list(tmp_path, "check"), _list(tmp_path, "rebuild")
    _write(b if which == "a" else a, rows)
    _refuses(tmp_path, a, b)
    assert "missing or empty" in capsys.readouterr().err


def test_a_refused_rerun_removes_an_earlier_passing_report(tmp_path: Path) -> None:
    # PR 227 review: a refused rerun must not leave the old "ok": true file for join35.py.
    rows = [_row("q1", ["a"])]
    a, b = _write(_list(tmp_path, "check"), rows), _write(_list(tmp_path, "rebuild"), rows)
    old = tmp_path / "out" / "bioasq" / "rebuild.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"ok": True}))
    b.write_text("")
    _refuses(tmp_path, a, b, "--prefreeze")


def test_refuses_an_empty_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _write(_list(tmp_path, "check"), [_row("q1", ["a"])])
    b = _write(_list(tmp_path, "rebuild"), [])
    _refuses(tmp_path, a, b)
    assert "missing or empty" in capsys.readouterr().err


def test_refuses_a_question_count_other_than_the_frozen_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_row("q1", ["a"]), _row("q2", ["b"])]
    a, b = _write(_list(tmp_path, "check"), rows), _write(_list(tmp_path, "rebuild"), rows)
    _refuses(tmp_path, a, b)  # bioasq freezes 707 questions
    assert "707" in capsys.readouterr().err


def test_a_prefreeze_subset_skips_the_count_and_is_marked(tmp_path: Path) -> None:
    rows = [_row("q1", ["a"])]
    a, b = _write(_list(tmp_path, "check"), rows), _write(_list(tmp_path, "rebuild"), rows)
    out = tmp_path / "out"
    code = rebuild35.main(
        ["--a", str(a), "--b", str(b), "--out-dir", str(out), "--dataset", "bioasq", "--prefreeze"]
    )
    report = json.loads((out / "bioasq" / "rebuild.json").read_text())
    assert code == 0 and report["prefreeze"] is True and report["questions_compared"] == 1


@pytest.mark.parametrize("which", ["a", "b"])
def test_refuses_a_list_of_another_setup(
    tmp_path: Path, which: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_row("q1", ["a"])]
    a, b = _list(tmp_path, "check"), _list(tmp_path, "rebuild")
    wrong = tmp_path / "x" / "bioasq" / "search" / "e4b-c512-roff-hoff" / "run1" / "search.jsonl"
    a, b = (wrong, b) if which == "a" else (a, wrong)
    _write(a, rows), _write(b, rows)
    _refuses(tmp_path, a, b, "--prefreeze")
    assert f"search/{SETUP}/" in capsys.readouterr().err
