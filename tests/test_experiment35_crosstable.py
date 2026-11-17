"""Experiment 35 floor, ceiling and miss cross-table, ``crosstable35.py`` (task 15.16; PR 13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load, open_half_b

crosstable35 = load("crosstable35")

RAG = "e4b-c512-roff-hoff"
T20K = "e4b-c512-r4b-hon-t20k"


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _single(out: Path, kind: str, scores: dict[str, float]) -> None:
    folder = out / "bioasq" / kind / RAG / "run1"
    _write(folder / "answer.jsonl", [{"qid": q, "answer": "a", "evidence": []} for q in scores])
    ragas = [
        {"qid": q, "metrics": {"ragas_answer_correctness": {"score": s}}} for q, s in scores.items()
    ]
    _write(folder / "ragas.jsonl", ragas)


def _build(out: Path) -> None:
    rag = {
        "q1": (0.9, 0.8, 0.7),
        "q2": (0.2, 0.3, 0.1),
        "q3": (0.9, 0.9, 0.9),
        "q4": (0.1, 0.1, 0.1),
    }
    rows = [
        {
            "dataset": "bioasq",
            "setup": setup,
            "run": run,
            "qid": q,
            "ragas_answer_correctness": values[run - 1],
        }
        for setup in (RAG, T20K)
        for q, values in rag.items()
        for run in (1, 2, 3)
    ]
    _write(out / "answer-scores.jsonl", rows)
    # Retrieval misses: q1, q2 and q4 have no gold unit in the evidence of RAG.
    # q2's gold unit sits past chunk 10: a recall_at_10 hit the answer model never saw.
    search = [
        {"qid": q, "recall_at_10": r, "head_recall_10": h, "evidence_recall_20k": e}
        for q, r, h, e in (
            ("q1", 0.0, 0.0, 0.0),
            ("q2", 1.0, 0.0, 1.0),
            ("q3", 1.0, 1.0, 1.0),
            ("q4", 0.0, 0.0, 0.0),
        )
    ]
    _write(out / "scores" / "A" / "bioasq" / "e4b-c512-roff-hoff.jsonl", search[:2])
    _write(out / "scores" / "B" / "bioasq" / "e4b-c512-roff-hoff.jsonl", search[2:])
    _write(out / "scores" / "A" / "bioasq" / "e4b-c512-r4b-hon.jsonl", search[:2])
    _write(out / "scores" / "B" / "bioasq" / "e4b-c512-r4b-hon.jsonl", search[2:])
    _single(out, "closedbook-own", {"q1": 0.9, "q2": 0.9, "q3": 0.1, "q4": 0.1})
    _single(out, "oracle", {"q1": 1.0, "q2": 1.0, "q3": 1.0, "q4": 0.0})


def test_floor_and_ceiling_rows_are_marked_single_run_beside_three_run_means(tmp_path) -> None:
    _build(tmp_path)
    table = crosstable35.build_tables(tmp_path)
    rows = {
        r["setup"] if r["kind"] == "rag" else r["kind"]: r for r in table["floor_ceiling"]["bioasq"]
    }
    assert rows[RAG]["runs"] == 3 and rows[RAG]["single_run"] is False
    assert rows[RAG]["correctness"] == (0.8 + 0.2 + 0.9 + 0.1) / 4
    assert rows["closedbook-own"]["runs"] == 1 and rows["closedbook-own"]["single_run"] is True
    assert rows["closedbook-own"]["correctness"] == 0.5
    assert rows["oracle"]["single_run"] is True and rows["oracle"]["correctness"] == 0.75


def test_miss_crosstable_counts_closed_book_against_rag_on_misses(tmp_path) -> None:
    _build(tmp_path)
    cross = crosstable35.build_tables(tmp_path)["miss_crosstable"]["bioasq"]
    # RAG setup misses q1, q2 and q4 (head_recall_10 == 0).
    assert cross[RAG] == {
        "misses_total": 3,
        "no_rag_score": 0,
        "no_closed_book_score": 0,
        "misses": 3,
        "closed_book_correct_rag_correct": 1,
        "closed_book_correct_rag_wrong": 1,
        "closed_book_wrong_rag_correct": 0,
        "closed_book_wrong_rag_wrong": 1,
    }
    # The t20k setup uses the token-cut evidence: it misses q1 and q4 only.
    assert cross[T20K]["misses"] == 2


def test_misses_without_a_score_are_counted(tmp_path) -> None:
    # Review R3-13: q1 has no RAG correctness (every run unjudged) and q2 no closed-book
    # score; both are misses, leave the table and are counted.
    _build(tmp_path)
    rows = [
        json.loads(line) for line in (tmp_path / "answer-scores.jsonl").read_text().splitlines()
    ]
    for row in rows:
        if row["qid"] == "q1":
            row["ragas_answer_correctness"] = None
    _write(tmp_path / "answer-scores.jsonl", rows)
    _single(tmp_path, "closedbook-own", {"q1": 0.9, "q3": 0.1, "q4": 0.1})
    cross = crosstable35.build_tables(tmp_path)["miss_crosstable"]["bioasq"][RAG]
    assert cross["misses_total"] == 3
    assert (cross["no_rag_score"], cross["no_closed_book_score"]) == (1, 1)
    assert cross["misses"] == 1  # q4 only


def test_an_unjudged_run_drops_the_rag_cell_as_in_the_analysis(tmp_path) -> None:
    # Section 12: an unjudged run (Ragas closed missing) leaves the complete cases;
    # the other runs do not stand in for it (review R3-03).
    _build(tmp_path)
    rows = [
        json.loads(line) for line in (tmp_path / "answer-scores.jsonl").read_text().splitlines()
    ]
    for row in rows:
        if row["qid"] == "q4" and row["setup"] == RAG and row["run"] == 2:
            row.update(ragas_answer_correctness=None, unjudged=["ragas_answer_correctness"])
    _write(tmp_path / "answer-scores.jsonl", rows)
    cross = crosstable35.build_tables(tmp_path)["miss_crosstable"]["bioasq"][RAG]
    assert (cross["misses"], cross["no_rag_score"]) == (2, 1)


def test_main_refuses_while_half_b_is_locked(tmp_path) -> None:
    _build(tmp_path)
    with pytest.raises(load("scoring35").HalfBLocked):
        crosstable35.main(["--out-dir", str(tmp_path)])
    assert not (tmp_path / "crosstable.json").exists()


def test_main_writes_the_table(tmp_path) -> None:
    _build(tmp_path)
    open_half_b(tmp_path)
    assert crosstable35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "crosstable.json").read_text())
    assert saved["cut"] == 0.5 and "bioasq" in saved["miss_crosstable"]
