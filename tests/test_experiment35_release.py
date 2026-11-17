"""Experiment 35 release kit (task 16.21, pre-registration section 19; H-25).

``release35.py`` exports ranked lists in TREC run format (unit IDs and a
rank-derived score, never corpus text) and rebuilds evidence text for a
re-judge from a rebuilt index and the released unit and chunk IDs. Fixtures
only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

release = load("release35")

CORPUS_TEXT = "the gross margin rose to forty one percent in the third quarter"


def _chunk(chunk_id: str, stem: str, page: str, score: float) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "stem": stem,
        "page_label": page,
        "score": score,
        "text": CORPUS_TEXT,
    }


# --- TREC run export -------------------------------------------------------------------


def _saved() -> dict[str, list[dict[str, Any]]]:
    # q1: two tied RRF scores; the saved order puts "B#p2" before "A#p1".
    return {
        "q1": [
            _chunk("c1", "B", "2", 0.5),
            _chunk("c2", "A", "1", 0.5),
            _chunk("c3", "B", "2", 0.4),  # same unit as c1: dropped
            _chunk("c4", "C", "9", 0.1),
        ],
        "q2": [_chunk("c9", "A", "3", 0.9)],
    }


def test_trec_lines_carry_a_strictly_decreasing_rank_score_and_no_text() -> None:
    lines = release.trec_run("financebench", _saved(), tag="e4b-c1024-roff-hoff")
    assert lines == [
        "q1 Q0 B#p2 1 999 e4b-c1024-roff-hoff",
        "q1 Q0 A#p1 2 998 e4b-c1024-roff-hoff",
        "q1 Q0 C#p9 3 997 e4b-c1024-roff-hoff",
        "q2 Q0 A#p3 1 999 e4b-c1024-roff-hoff",
    ]
    assert all(CORPUS_TEXT.split()[1] not in line for line in lines)


def test_tied_input_scores_keep_the_saved_order_after_a_trec_eval_sort() -> None:
    lines = release.trec_run("financebench", _saved(), tag="t")
    rows = [line.split() for line in lines if line.startswith("q1 ")]
    # trec_eval sorts by score, high first, then by document ID in reverse order.
    rows.sort(key=lambda r: r[2], reverse=True)
    rows.sort(key=lambda r: float(r[4]), reverse=True)
    assert [r[2] for r in rows] == ["B#p2", "A#p1", "C#p9"]


def test_trec_export_writes_the_file(tmp_path: Path) -> None:
    out = tmp_path / "run.trec"
    release.write_trec_run(out, "financebench", _saved(), tag="t")
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "q1 Q0 B#p2 1 999 t"
    assert CORPUS_TEXT not in text


# --- re-judge kit ----------------------------------------------------------------------


class _Store:
    """A rebuilt index with two stored chunks."""

    def iter_documents(self, collection_name: str) -> Iterator[tuple[str, str, dict[str, Any]]]:
        assert collection_name == "fb-e4b-c1024"
        yield "c1", "Revenue was 12 million.", {"file_name": "B.md", "page_label": "2"}
        yield "c2", "Costs fell.", {"file_name": "A.md", "page_label": "1"}
        yield "c7", "Not cited.", {"file_name": "A.md", "page_label": "5"}


def _released(**evidence: str) -> list[dict[str, Any]]:
    items = [{"chunk_id": cid, "unit": unit} for cid, unit in evidence.items()]
    return [{"dataset": "financebench", "setup": "s", "run": 1, "qid": "q1", "evidence": items}]


def test_read_chunks_keeps_only_the_named_ids() -> None:
    chunks = release.read_chunks(_Store(), "fb-e4b-c1024", {"c1", "c2"})
    assert sorted(chunks) == ["c1", "c2"]
    assert chunks["c1"]["text"] == "Revenue was 12 million."
    assert chunks["c1"]["page_label"] == "2"


def test_rejudge_rebuilds_evidence_text_from_the_released_ids() -> None:
    chunks = release.read_chunks(_Store(), "fb-e4b-c1024", {"c1", "c2"})
    (row,) = release.rebuild_evidence(_released(c1="B#p2", c2="A#p1"), chunks)
    assert row["qid"] == "q1" and row["run"] == 1
    assert row["evidence"] == [
        {"chunk_id": "c1", "unit": "B#p2", "text": "Revenue was 12 million."},
        {"chunk_id": "c2", "unit": "A#p1", "text": "Costs fell."},
    ]


def test_rejudge_refuses_a_chunk_missing_from_the_rebuilt_index() -> None:
    chunks = release.read_chunks(_Store(), "fb-e4b-c1024", {"c1"})
    with pytest.raises(ValueError, match="c8"):
        release.rebuild_evidence(_released(c1="B#p2", c8="A#p1"), chunks)


def test_rejudge_refuses_a_chunk_whose_unit_differs() -> None:
    chunks = release.read_chunks(_Store(), "fb-e4b-c1024", {"c1"})
    with pytest.raises(ValueError, match=r"c1.*B#p3.*B#p2"):
        release.rebuild_evidence(_released(c1="B#p3"), chunks)


def test_rejudge_writes_a_local_file(tmp_path: Path) -> None:
    released = tmp_path / "evidence.jsonl"
    released.write_text(json.dumps(_released(c2="A#p1")[0]) + "\n", encoding="utf-8")
    out = tmp_path / "local" / "rejudge.jsonl"
    release.run_rejudge(released, _Store(), "fb-e4b-c1024", out)
    (line,) = out.read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["evidence"][0]["text"] == "Costs fell."
