"""Experiment 35 G1 determinism stage, ``determinism35.py`` (task 6.3; A5 R-2, H-05, H-21).

G1 compares each answer run's saved ranked list of 100 stored chunk IDs
(``run<n>/retrieval.jsonl``) with the single search-stage run of the matching
search setup, and checks that the evidence IDs are the head of that list.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests._exp35_fixtures import load

determinism35 = load("determinism35")
outputs35 = load("outputs35")
stages35 = load("stages35")

QIDS = ("q1", "q2")


def _ids(prefix: str, n: int = 12) -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def _line(qid: str, ids: list[str], tokens: int = 100) -> dict:
    return {"qid": qid, "chunks": [{"chunk_id": i, "tokens": tokens} for i in ids]}


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _answer(qid: str, ids: list[str]) -> dict:
    # Two adjacent kept chunks merged into one evidence item, in chunk order.
    items = [{"ordinal": 1, "chunk_ids": [ids[1], ids[0]]}]
    items += [{"ordinal": n + 1, "chunk_ids": [i]} for n, i in enumerate(ids[2:], start=1)]
    return {"qid": qid, "answer": "x", "evidence": items}


def _build(out: Path, setup: str = "e4b-c512-r4b-hoff", search: str | None = None) -> None:
    (out / "join.json").write_text(json.dumps({"ok": True}))
    lists = {q: _ids(q) for q in QIDS}
    _write(
        out / "bioasq" / "search" / (search or setup) / "run1" / "search.jsonl",
        [_line(q, lists[q]) for q in QIDS],
    )
    for run in (1, 2, 3):
        folder = out / "bioasq" / "answer" / setup / f"run{run}"
        _write(folder / "retrieval.jsonl", [_line(q, lists[q]) for q in QIDS])
        _write(folder / "answer.jsonl", [_answer(q, lists[q][:10]) for q in QIDS])
        _write(folder / "machine.jsonl", [{"host": f"pod{run}", "pod_id": f"id{run}"}])


def _ctx(out: Path, setup: str = "e4b-c512-r4b-hoff", run: int = 1) -> SimpleNamespace:
    questions = [SimpleNamespace(qid=q) for q in QIDS]
    return SimpleNamespace(
        layout=outputs35.Layout(out), dataset="bioasq", setup=setup, run=run, questions=questions
    )


def _run(out: Path, setup: str = "e4b-c512-r4b-hoff", run: int = 1) -> tuple[int, dict]:
    code = asyncio.run(determinism35.determinism_stage(_ctx(out, setup, run)))
    path = out / "bioasq" / "answer" / setup / f"run{run}" / "determinism.json"
    return code, json.loads(path.read_text())


def test_runs_on_a_replicate_pod_with_no_join(tmp_path: Path) -> None:
    # Review S3: G1 runs right after each pod's answer stage, so it can stop the run early.
    _build(tmp_path)
    (tmp_path / "join.json").unlink()
    for run in (1, 2, 3):
        code, report = _run(tmp_path, run=run)
        assert code == 0 and report["ok"] is True and report["run"] == run
        assert report["machines"] == [{"host": f"pod{run}", "pod_id": f"id{run}"}]
    assert report["search_setup"] == "e4b-c512-r4b-hoff"


def test_a_t20k_setup_maps_to_its_hybrid_on_search_setup(tmp_path: Path) -> None:
    setup = "e4b-c512-r4b-hon-t20k"
    _build(tmp_path, setup, search="e4b-c512-r4b-hon")
    # Token cut: 12 chunks of 100 tokens are all under 20,480, so the head is all 12.
    for run in (1, 2, 3):
        folder = tmp_path / "bioasq" / "answer" / setup / f"run{run}"
        _write(folder / "answer.jsonl", [_answer(q, _ids(q)) for q in QIDS])
    code, report = _run(tmp_path, setup)
    assert code == 0, report
    assert report["search_setup"] == "e4b-c512-r4b-hon"


def test_a_run_list_that_differs_from_the_search_list_fails_that_run_only(tmp_path: Path) -> None:
    _build(tmp_path)
    folder = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff" / "run2"
    swapped = _ids("q1")
    swapped[11], swapped[10] = swapped[10], swapped[11]
    _write(folder / "retrieval.jsonl", [_line("q1", swapped), _line("q2", _ids("q2"))])
    code, report = _run(tmp_path, run=2)
    assert code == determinism35.EXIT_MISMATCH
    assert report["ok"] is False
    assert report["lists"]["mismatches"][0]["question_id"] == "q1"
    assert report["lists"]["mismatches"][0]["differing_runs"] == ["run2"]
    assert _run(tmp_path, run=1)[0] == 0


def test_evidence_that_is_not_the_head_fails(tmp_path: Path) -> None:
    _build(tmp_path)
    folder = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff" / "run3"
    ids = _ids("q2")
    _write(folder / "answer.jsonl", [_answer("q1", _ids("q1")[:10]), _answer("q2", ids[1:11])])
    code, report = _run(tmp_path, run=3)
    assert code == determinism35.EXIT_MISMATCH
    assert report["evidence_mismatches"] == [{"run": 3, "question_id": "q2"}]


@pytest.mark.parametrize("where", ["search", "run"])
def test_a_failed_search_on_either_side_is_incomplete_never_a_match(
    tmp_path: Path, where: str
) -> None:
    _build(tmp_path)
    if where == "search":
        path = tmp_path / "bioasq" / "search" / "e4b-c512-r4b-hoff" / "run1" / "search.jsonl"
        _write(path, [_line("q1", _ids("q1")), {"qid": "q2", "missing": True, "error": "x"}])
        both = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff"
        for run in (1, 2, 3):
            _write(
                both / f"run{run}" / "retrieval.jsonl", [_line("q1", _ids("q1")), _line("q2", [])]
            )
            answers = [_answer("q1", _ids("q1")[:10]), {"qid": "q2", "missing": True}]
            _write(both / f"run{run}" / "answer.jsonl", answers)
    else:
        folder = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff" / "run1"
        _write(folder / "retrieval.jsonl", [_line("q1", _ids("q1"))])
    code, report = _run(tmp_path)
    assert code == determinism35.EXIT_MISMATCH
    assert report["ok"] is False
    assert [i["question_id"] for i in report["lists"]["incomplete"]] == ["q2"]


@pytest.mark.parametrize(
    "missing",
    ["answer/e4b-c512-r4b-hoff/run1/answer.jsonl", "search/e4b-c512-r4b-hoff/run1/search.jsonl"],
)
def test_refuses_and_names_a_missing_run_file(tmp_path: Path, missing: str) -> None:
    _build(tmp_path)
    (tmp_path / "bioasq" / missing).unlink()
    with pytest.raises(stages35.StageOrderError, match=missing.split("/")[-2]):
        asyncio.run(determinism35.determinism_stage(_ctx(tmp_path)))
    run_dir = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff" / "run1"
    assert not (run_dir / "determinism.json").exists()


# --- the analysis guard: every run of every setup passed G1 ------------------------------


def _all_runs(out: Path) -> None:
    for run in (1, 2, 3):
        assert _run(out, run=run)[0] == 0


def test_require_g1_passes_when_every_run_passed(tmp_path: Path) -> None:
    _build(tmp_path)
    _all_runs(tmp_path)
    determinism35.require_g1(tmp_path, {"bioasq": ["e4b-c512-r4b-hoff"]})


@pytest.mark.parametrize("change", ["missing", "fails"])
def test_require_g1_refuses_a_missing_or_failed_run(tmp_path: Path, change: str) -> None:
    _build(tmp_path)
    _all_runs(tmp_path)
    path = tmp_path / "bioasq" / "answer" / "e4b-c512-r4b-hoff" / "run2" / "determinism.json"
    if change == "missing":
        path.unlink()
    else:
        path.write_text(json.dumps({"ok": False}))
    with pytest.raises(determinism35.G1NotPassed, match="run2"):
        determinism35.require_g1(tmp_path, {"bioasq": ["e4b-c512-r4b-hoff"]})
