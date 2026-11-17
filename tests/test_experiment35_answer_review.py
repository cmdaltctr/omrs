"""Experiment 35 answer, closed-book and oracle stages: fixes from review R2.

Rules under test: searches run one at a time while the paid answer calls run in
parallel (R2-02); a dataset dropped by step 1 gets no answers (R2-07); a cut
last line of ``retrieval.jsonl`` is repaired (R2-09); the dispatch record is
written just before the paid call (R2-10); the closed-book and oracle stages
use the selection check and the half-B guard (R2-04).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, stage_ctx
from tests.test_experiment35_parallel_answers import Engine, _ctx, _lines, _questions, _run

closedbook35 = load("closedbook35")
oracle35 = load("oracle35")
outputs35 = load("outputs35")
stages35 = load("stages35")

SETUP = "e4b-c1024-r4b-hon"


class Flight(Engine):
    """Counts searches and answers in flight; answers wait until *limit* are in flight."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.lock = threading.Lock()
        self.searching = 0
        self.most_searches = 0
        self.answering = 0
        self.most_answers = 0
        self.full: asyncio.Event | None = None

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        with self.lock:
            self.searching += 1
            self.most_searches = max(self.most_searches, self.searching)
        time.sleep(0.01)
        try:
            return super().search(text, **kwargs)
        finally:
            with self.lock:
                self.searching -= 1

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.full = self.full or asyncio.Event()
        self.answering += 1
        self.most_answers = max(self.most_answers, self.answering)
        if self.answering == self.limit:
            self.full.set()
        await asyncio.wait_for(self.full.wait(), 5)
        try:
            return await super().answer(text, **kwargs)
        finally:
            self.answering -= 1


def test_searches_run_one_at_a_time_while_answers_run_at_the_set_concurrency(
    tmp_path: Path,
) -> None:
    engine = Flight(limit=4)
    ctx = _ctx(tmp_path, engine, args={"answer_concurrency": 4})
    assert _run(ctx) == 0
    assert engine.most_searches == 1
    assert engine.most_answers == 4


def test_a_dataset_dropped_by_step_1_gets_no_answer_and_no_file(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine, dataset="legal")
    outputs35.write_json(ctx.layout.root / "drops.json", {"drops": [{"step": 1}]})
    assert _run(ctx) == 0
    assert engine.searches == [] and engine.answers == []
    assert not ctx.run_dir.exists()


def test_a_drop_step_1_leaves_the_other_datasets_alone(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    outputs35.write_json(ctx.layout.root / "drops.json", {"drops": [{"step": 1}]})
    assert _run(ctx) == 0
    assert len(engine.answers) == 4


def test_a_cut_last_line_of_retrieval_jsonl_is_repaired_on_resume(tmp_path: Path) -> None:
    engine = Engine()
    engine.fail_search.add("question 2?")
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    ctx = _ctx(tmp_path, engine, resume=True)
    path = ctx.run_dir / "retrieval.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"qid": "q2", "chu', encoding="utf-8")
    engine.fail_search.clear()
    assert _run(ctx) == 0
    assert [r["qid"] for r in _lines(path)] == ["q0", "q1", "q2", "q3"]


def test_a_failed_search_is_not_counted_as_a_resent_paid_call(tmp_path: Path) -> None:
    engine = Engine()
    engine.fail_search.add("question 2?")
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    engine.fail_search.clear()
    ctx = _ctx(tmp_path, engine, resume=True)
    assert _run(ctx) == 0
    marker = json.loads((ctx.run_dir / ".done-answer.json").read_text(encoding="utf-8"))
    assert marker["resent_calls"] == 0


# --- closed-book and oracle guards (R2-04) ----------------------------------------------


class Model:
    """Stub engine for the closed-book and oracle stages: counts the answer calls."""

    store = None

    def __init__(self) -> None:
        self.calls = 0

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"status": "answered", "answer": "A."}


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    async def ask(engine: Any, collection: str, prompt: str) -> dict[str, Any]:
        prompts.append(prompt)
        return {"status": "answered", "answer": "Paris"}

    monkeypatch.setattr(closedbook35, "ask", ask)
    return prompts


def _stage(tmp_path: Path, kind: str, **args: Any) -> Any:
    engine = Model()
    ctx = stage_ctx(
        tmp_path, kind, SETUP, kind=kind, questions=_questions(), engine=engine, args=args
    )
    return ctx, engine


def _go(kind: str, ctx: Any) -> int:
    module = closedbook35.closedbook_stage if kind == "closedbook" else oracle35.oracle_stage
    return asyncio.run(module(ctx))


@pytest.mark.parametrize("kind", ["closedbook", "oracle"])
def test_closed_book_and_oracle_refuse_without_the_selection(
    tmp_path: Path, asked: list[str], kind: str
) -> None:
    ctx, engine = _stage(tmp_path, kind)
    (ctx.layout.root / "selection.json").unlink()
    with pytest.raises(stages35.StageOrderError, match="selection.json"):
        _go(kind, ctx)
    assert asked == [] and engine.calls == 0


@pytest.mark.parametrize("kind", ["closedbook", "oracle"])
def test_closed_book_and_oracle_refuse_while_half_b_is_locked(
    tmp_path: Path, asked: list[str], kind: str
) -> None:
    ctx, engine = _stage(tmp_path, kind)
    path = ctx.layout.root / "selection.json"
    path.write_text(json.dumps({"embedder": "4b", "reranker": "4b", "configuration_hash": "a"}))
    (ctx.layout.root / "osf-timestamp.json").unlink()
    with pytest.raises(load("scoring35").HalfBLocked):
        _go(kind, ctx)
    assert asked == [] and engine.calls == 0


def test_each_retrieval_line_goes_through_the_synced_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers35 = load("answers35")
    written: list[str] = []
    real = answers35.append_line

    def spy(path: Path, record: Any) -> None:
        written.append(path.name)
        real(path, record)

    monkeypatch.setattr(answers35, "append_line", spy)
    assert _run(_ctx(tmp_path, Engine())) == 0
    assert written.count("retrieval.jsonl") == 4
