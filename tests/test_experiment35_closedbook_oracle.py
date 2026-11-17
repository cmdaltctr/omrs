"""Experiment 35 closed-book and oracle stages (tasks 15.4 stage part, 15.12, 15.13).

Stub answer model and stub engine; the oracle units come from the prepared
passage files of the tmp data folder. No search call, no network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import FakeTokens, fake_plan, load, make_data_root, stage_ctx

from omrs.core.answer.stages import prepare_evidence

closedbook35 = load("closedbook35")
datasets35 = load("datasets35")
oracle35 = load("oracle35")
outputs35 = load("outputs35")
prepare35 = load("prepare35")
stagekit35 = load("stagekit35")
stages35 = load("stages35")

SETUP = "e4b-c1024-r4b-hon"


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stagekit35, "clock", lambda: 0.0)


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


class Engine:
    """Stub engine: any search call fails the test; ``answer`` records its rows."""

    store = None

    def __init__(self) -> None:
        self.answers: list[list[dict[str, Any]]] = []

    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no search call is allowed")

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.answers.append(list(kwargs["rows"]))
        return {
            "status": "answered",
            "answer": "A [1].",
            "evidence": prepare_evidence(kwargs["rows"]),
            "diagnostics": {"completion_calls": 1},
        }


# --- closed-book (task 15.4 stage part) ---------------------------------------------------


def _questions(n: int = 3) -> list[Any]:
    return [datasets35.Question(qid=f"q{i}", text=f"question {i}?", relevant=()) for i in range(n)]


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    async def ask(engine: Any, collection: str, prompt: str) -> dict[str, Any]:
        prompts.append(prompt)
        return {"status": "answered", "answer": "Paris", "usage": {"input_tokens": 9}}

    monkeypatch.setattr(closedbook35, "ask", ask)
    return prompts


@pytest.mark.parametrize("dataset", ["financebench", "freshstack", "bioasq", "legal"])
def test_closed_book_runs_both_prompts_once_per_question_with_no_search(
    tmp_path: Path, asked: list[str], dataset: str
) -> None:
    ctx = stage_ctx(
        tmp_path, "closedbook", SETUP, kind="closedbook", questions=_questions(),
        engine=Engine(), dataset=dataset,
    )  # fmt: skip
    assert asyncio.run(closedbook35.closedbook_stage(ctx)) == 0
    assert len(asked) == 6
    for kind in ("own", "rag"):
        folder = ctx.layout.run_dir(dataset, f"closedbook-{kind}", SETUP, 1)
        rows = _lines(folder / "answer.jsonl")
        assert [r["qid"] for r in rows] == ["q0", "q1", "q2"]
        assert all(
            r["prompt"] == kind and r["evidence"] == [] and r["completion_calls"] == 1 for r in rows
        )
        assert (folder / ".done-answer.json").exists()
    assert asked[0] == closedbook35.OWN_PROMPT.format(query="question 0?")
    assert "---------------------\n\n---------------------" in asked[3]
    asked.clear()
    ctx.resume = True
    assert asyncio.run(closedbook35.closedbook_stage(ctx)) == 0
    assert asked == []


def test_a_recorded_drop_step_3_skips_the_rag_prompt_run(tmp_path: Path, asked: list[str]) -> None:
    ctx = stage_ctx(
        tmp_path, "closedbook", SETUP, kind="closedbook", questions=_questions(), engine=Engine()
    )
    outputs35.write_json(ctx.layout.root / "drops.json", {"drops": [{"step": 3}]})
    assert asyncio.run(closedbook35.closedbook_stage(ctx)) == 0
    assert len(asked) == 3
    assert not ctx.layout.run_dir("bioasq", "closedbook-rag", SETUP, 1).exists()


def test_closed_book_and_oracle_refuse_another_run_than_1(tmp_path: Path) -> None:
    for module, stage in ((closedbook35, "closedbook_stage"), (oracle35, "oracle_stage")):
        ctx = stage_ctx(tmp_path, "x", SETUP, kind="oracle", questions=_questions(), run=2)
        with pytest.raises(stages35.StageOrderError, match="run 1"):
            asyncio.run(getattr(module, stage)(ctx))


# --- oracle contexts (task 15.12) and the oracle stage (task 15.13) -----------------------


@pytest.fixture
def prepared(tmp_path: Path) -> tuple[Path, Path]:
    root = make_data_root(tmp_path / "DATA")
    passages = tmp_path / "passages"
    for dataset in ("freshstack", "bioasq", "legal"):
        prepare35.prepare(dataset, root, passages, plan=fake_plan())
    return root, passages


def test_oracle_units_come_from_the_prepared_files_in_gold_order(
    prepared: tuple[Path, Path],
) -> None:
    root, passages = prepared
    for dataset in ("legal", "bioasq", "freshstack"):
        question = datasets35.load_questions(dataset, root)[0]
        rows = oracle35.gold_rows(dataset, question, passages=passages, pages=None)
        assert [r["chunk_id"] for r in rows] == list(question.relevant)
        assert all(r["text"] for r in rows)
    legal = datasets35.load_questions("legal", root)[0]
    assert len(oracle35.gold_rows("legal", legal, passages=passages, pages=None)) == 1


def test_financebench_oracle_gives_the_gold_page_texts(prepared: tuple[Path, Path]) -> None:
    root, passages = prepared
    question = datasets35.load_questions("financebench", root)[2]
    seen: list[tuple[str, str]] = []

    def pages(doc: str, label: str) -> str:
        seen.append((doc, label))
        return f"page {label} of {doc}"

    rows = oracle35.gold_rows("financebench", question, passages=passages, pages=pages)
    assert [r["text"] for r in rows] == [f"page {lb} of {d}" for d, lb in seen]
    assert [f"{d}#p{lb}" for d, lb in seen] == list(question.relevant)


def test_a_missing_gold_unit_stops_and_names_it(prepared: tuple[Path, Path]) -> None:
    root, passages = prepared
    question = datasets35.Question(qid="x", text="?", relevant=("1000", "9999"))
    with pytest.raises(datasets35.DatasetError, match="9999"):
        oracle35.gold_rows("bioasq", question, passages=passages, pages=None)
    question = datasets35.Question(qid="x", text="?", relevant=("ACME_2020_10K#p7",))
    with pytest.raises(datasets35.DatasetError, match="ACME_2020_10K#p7"):
        oracle35.gold_rows("financebench", question, passages=passages, pages=lambda d, p: None)


@pytest.mark.parametrize("dataset", ["financebench", "freshstack", "bioasq", "legal"])
def test_every_oracle_context_is_capped_at_20480_tokens_with_truncation_recorded(
    dataset: str,
) -> None:
    rows = [{"chunk_id": f"u{i}", "text": " ".join(["t"] * 9000)} for i in range(3)]
    kept, record = oracle35.oracle_context(rows, FakeTokens())
    assert record["tokens"] == 20_480
    assert sum(FakeTokens.count(r["text"]) for r in kept) == 20_480
    assert record["truncated"] == ["u2"] and record["tokens_dropped"] == 27_000 - 20_480
    short, record = oracle35.oracle_context(rows[:1], FakeTokens())
    assert record["truncated"] == [] and record["tokens_dropped"] == 0 and len(short) == 1


def test_the_oracle_stage_answers_from_gold_units_once_with_no_search(
    tmp_path: Path, prepared: tuple[Path, Path]
) -> None:
    root, passages = prepared
    questions = datasets35.load_questions("bioasq", root)[:3]
    engine = Engine()
    ctx = stage_ctx(
        tmp_path, "oracle", SETUP, kind="oracle", questions=questions, engine=engine,
        args={"passages_dir": passages},
    )  # fmt: skip
    assert asyncio.run(oracle35.oracle_stage(ctx)) == 0
    rows = _lines(ctx.run_dir / "answer.jsonl")
    assert [r["qid"] for r in rows] == [q.qid for q in questions]
    assert rows[0]["oracle"]["units"] == list(questions[0].relevant)
    assert [e["chunk_id"] for e in rows[0]["evidence"]] == list(questions[0].relevant)
    assert (ctx.run_dir / ".done-answer.json").exists()
    assert ctx.run_dir.parts[-3:] == ("oracle", SETUP, "run1")
    assert len(engine.answers) == 3


def test_each_closed_book_prompt_writes_its_own_trace(tmp_path: Path, asked: list[str]) -> None:
    ctx = stage_ctx(
        tmp_path, "closedbook", SETUP, kind="closedbook", questions=_questions(), engine=Engine()
    )
    assert asyncio.run(closedbook35.closedbook_stage(ctx)) == 0
    for kind in ("own", "rag"):
        folder = ctx.layout.run_dir("bioasq", f"closedbook-{kind}", SETUP, 1)
        assert [r["question_id"] for r in _lines(folder / "traces.jsonl")] == ["q0", "q1", "q2"]
