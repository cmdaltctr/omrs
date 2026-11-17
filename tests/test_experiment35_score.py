"""Experiment 35 ``score35.py``: scores saved search lists per half (tasks 15.1a, 16.17).

The search stage saves ranked lists only. ``score35.py`` reads them with the
gold labels and scores one half at a time; half B runs behind the guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load

score35 = load("score35")
scoring35 = load("scoring35")

SETUP = "e4b-c512-roff-hoff"
HALVES = {"bioasq": {"q1": "A", "q2": "B", "q3": "A", "q4": "B"}}


def _chunk(cid: str, stem: str, tokens: int = 100) -> dict:
    return {"chunk_id": cid, "score": 0.5, "stem": stem, "page_label": None, "tokens": tokens}


def _build(out: Path, rows: list[dict]) -> Path:
    folder = out / "bioasq" / "search" / SETUP / "run1"
    folder.mkdir(parents=True)
    (folder / "search.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return folder


def _rows() -> list[dict]:
    return [
        {"qid": "q1", "chunks": [_chunk("c1", "p1"), _chunk("c2", "x")]},
        {"qid": "q2", "chunks": [_chunk("c3", "y"), _chunk("c4", "p2")]},
        {"qid": "q3", "missing": True, "error": "boom"},
        {"qid": "q4", "chunks": [_chunk("c5", "p4")]},
    ]


def _golds() -> dict:
    gold = scoring35.Gold
    return {"bioasq": {q: gold(q, frozenset({f"p{q[1]}"})) for q in ("q1", "q2", "q3", "q4")}}


def _stamp(out: Path) -> None:
    (out / "selection.json").write_text(json.dumps({"configuration_hash": "a" * 64}))
    stamp = {"uploaded_at": "t", "file_sha256": "f" * 64, "configuration_hash": "a" * 64}
    (out / "osf-timestamp.json").write_text(json.dumps(stamp))


def test_half_a_scores_only_half_a_questions(tmp_path: Path) -> None:
    _build(tmp_path, _rows())
    summary = score35.score(tmp_path, "A", halves=HALVES, golds=_golds())
    lines = (tmp_path / "scores" / "A" / "bioasq" / f"{SETUP}.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["qid"] for r in records] == ["q1", "q3"]
    assert records[0]["ndcg_at_10"] == 1.0
    assert records[1]["ndcg_at_10"] == 0.0  # a search still missing scores 0 (section 12)
    assert summary["bioasq"][SETUP]["n"] == 2
    assert summary["bioasq"][SETUP]["missing"] == ["q3"]
    saved = json.loads((tmp_path / "scores" / "A" / "bioasq" / "summary.json").read_text())
    assert saved[SETUP]["ndcg_at_10"] == pytest.approx(0.5)


def test_half_b_refuses_before_any_score_and_writes_nothing(tmp_path: Path) -> None:
    _build(tmp_path, _rows())
    before = sorted(p for p in tmp_path.rglob("*"))
    with pytest.raises(scoring35.HalfBLocked, match="selection.json"):
        score35.score(tmp_path, "B", halves=HALVES, golds={})
    assert sorted(p for p in tmp_path.rglob("*")) == before


def test_half_b_scores_once_the_hash_is_time_stamped(tmp_path: Path) -> None:
    _build(tmp_path, _rows())
    _stamp(tmp_path)
    score35.score(tmp_path, "B", halves=HALVES, golds=_golds())
    lines = (tmp_path / "scores" / "B" / "bioasq" / f"{SETUP}.jsonl").read_text().splitlines()
    assert [json.loads(line)["qid"] for line in lines] == ["q2", "q4"]
    assert json.loads(lines[0])["mrr_at_10"] == 0.5


def test_evidence_recall_uses_the_saved_token_counts(tmp_path: Path) -> None:
    gold = {"bioasq": {"q1": scoring35.Gold("q1", frozenset({"p1", "p3"}))}}
    rows = [
        {
            "qid": "q1",
            "chunks": [_chunk("a", "p1", 15_000), _chunk("b", "p3", 10_000), _chunk("c", "x", 9)],
        }
    ]
    _build(tmp_path, rows)
    score35.score(tmp_path, "A", halves={"bioasq": {"q1": "A"}}, golds=gold)
    path = tmp_path / "scores" / "A" / "bioasq" / f"{SETUP}.jsonl"
    record = json.loads(path.read_text())
    assert record["evidence_chunks"] == 2  # the crossing chunk is kept, truncated
    assert record["evidence_recall_20k"] == 1.0


@pytest.mark.parametrize(
    ("tokens", "k"),
    [([100] * 10, 10), ([20_480, 5], 1), ([20_479, 5, 5], 2), ([10_000, 10_480, 1], 2), ([], 0)],
)
def test_token_cut_head_length(tokens: list[int], k: int) -> None:
    chunks = [{"chunk_id": str(i), "tokens": t} for i, t in enumerate(tokens)]
    assert score35.token_cut_k(chunks) == k


def test_main_reads_the_loaders_and_writes_half_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build(tmp_path, _rows())
    halves = tmp_path / "halves.json"
    halves.write_text(json.dumps({"seed": 1, "halves": HALVES}))
    datasets35 = load("datasets35")
    questions = [
        datasets35.Question(qid=q, text="t", relevant=(f"p{q[1]}",)) for q in ("q1", "q2", "q3")
    ]
    questions.append(datasets35.Question(qid="q4", text="t", relevant=("p4",)))
    monkeypatch.setattr(score35, "_questions", lambda dataset: questions)
    code = score35.main(["--out-dir", str(tmp_path), "--half", "A", "--halves", str(halves)])
    assert code == 0
    assert (tmp_path / "scores" / "A" / "bioasq" / f"{SETUP}.jsonl").exists()


def test_main_refuses_freshstack_without_the_passage_folder(tmp_path: Path) -> None:
    run = tmp_path / "freshstack" / "search" / "e4b-c512-roff-hoff" / "run1"
    run.mkdir(parents=True)
    (run / "search.jsonl").write_text("")
    halves = tmp_path / "halves.json"
    halves.write_text(json.dumps({"seed": 1, "halves": {"freshstack": {}}}))
    argv = ["--out-dir", str(tmp_path), "--half", "A", "--halves", str(halves)]
    with pytest.raises(SystemExit) as caught:
        score35.main(argv)
    assert caught.value.code == 2


def test_main_help_names_the_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        score35.main(["--help"])
    text = capsys.readouterr().out
    for option in ("--out-dir", "--half", "--halves", "--passages-dir"):
        assert option in text
