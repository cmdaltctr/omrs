"""Experiment 35 answer stage (``answers35.py``) with a stub engine on a sealed fixture index.

Rules under test: the order of work per question (task 4.2, A5 R-1); depth
100 and the head rule (tasks 15.2, 15.3, 15.14); the rate-limit and resend
rules (task 4.3, section 12); the evidence measures (task 14.2); the
``selection.json`` refusal (task 14.3); an un-reranked query (task 13.7).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.hosted_calls import RateLimitStop
from tests._exp35_fixtures import FakeTokens, load, open_half_b, stage_ctx

from omrs.core.answer.stages import prepare_evidence

answers35 = load("answers35")
arms = load("arms")
datasets35 = load("datasets35")
outputs35 = load("outputs35")
stagekit35 = load("stagekit35")
stages35 = load("stages35")

CROSSED = "e4b-c1024-r4b-hon"
T20K = "e4b-c1024-r4b-hon-t20k"
LIMITED = {"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 0.0}


def _questions(n: int = 4) -> list[Any]:
    return [datasets35.Question(qid=f"q{i}", text=f"question {i}?", relevant=()) for i in range(n)]


class Engine:
    """Stub engine: 100 ranked stored chunks; ``answer`` follows a script per question."""

    store = None

    def __init__(self, words: int = 3, script: dict[str, list[Any]] | None = None) -> None:
        self.words = words
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.searches: list[tuple[str, dict[str, Any]]] = []
        self.answers: list[tuple[str, list[dict[str, Any]]]] = []
        self.fail_search: set[str] = set()
        self.unranked: set[str] = set()
        #: Stored chunks that are neighbours in one source: rank to (source, chunk index).
        self.neighbours = {0: ("s0", 0), 1: ("s0", 1)}

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.searches.append((text, kwargs))
        if text in self.fail_search:
            raise RuntimeError("store unavailable")
        return [
            {
                "chunk_id": f"ch{i}",
                "text": " ".join([f"w{i}"] * self.words),
                "score": 1.0 - i / 1000,
                "page_label": None,
                "metadata": {"file_name": f"doc{i}.md"},
                "source": f"{self.neighbours.get(i, (f's{i}', 0))[0]}.md",
                "source_id": self.neighbours.get(i, (f"s{i}", 0))[0],
                "source_version": "v1",
                "source_chunk_index": self.neighbours.get(i, (f"s{i}", 0))[1],
                "source_chunk_count": 2,
                "reranked": text not in self.unranked,
            }
            for i in range(100)
        ]

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        rows = list(kwargs["rows"])
        self.answers.append((text, rows))
        await asyncio.sleep(0.001 * (9 - int(text.split()[1][0])))
        step = self.script.get(text, ["ok"]).pop(0) if self.script.get(text) else "ok"
        if step == "limited":
            return {"status": "error", "answer": None, "rate_limited": dict(LIMITED)}
        if step == "error":
            return {"status": "error", "answer": None, "error": "Generation failed: timeout"}
        if isinstance(step, Exception):
            raise step
        answer = "" if step == "empty" else ("I cannot answer." if step == "refusal" else "A [1].")
        return {
            "status": "answered",
            "answer": answer,
            "citations": [1],
            "evidence": prepare_evidence(rows),
            "usage": {"input_tokens": 10, "output_tokens": 2, "cost_usd": 0.001},
            "sampling": {
                "chat": {
                    "host": "h1",
                    "host_in_list": True,
                    "temperature": 0.0,
                    "model_returned": "deepseek/deepseek-v4.1-flash-1017",
                }
            },
            "diagnostics": {"completion_calls": 1},
        }


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stagekit35, "clock", lambda: 0.0)


def _select(ctx: Any, embedder: str = "4b", reranker: str = "4b") -> None:
    open_half_b(ctx.layout.root, embedder=embedder, reranker=reranker)


def _ctx(tmp_path: Path, engine: Engine, setup: str = CROSSED, **kw: Any) -> Any:
    ctx = stage_ctx(
        tmp_path, "answer", setup, kind="answer", questions=_questions(), engine=engine, **kw
    )
    _select(ctx)
    return ctx


def _run(ctx: Any) -> int:
    return asyncio.run(answers35.answer_stage(ctx))


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


# --- order of work (tasks 4.2, 15.2, 15.3) -----------------------------------------------


@pytest.mark.parametrize("chunk", [512, 1024, 2048])
def test_assembly_gets_the_setups_own_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chunk: int
) -> None:
    seen: list[dict[str, Any]] = []
    real = answers35.assemble

    def spy(rows: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return real(rows, **kwargs)

    monkeypatch.setattr(answers35, "assemble", spy)
    ctx = _ctx(tmp_path, Engine(), f"e4b-c{chunk}-r4b-hon")
    assert _run(ctx) == 0
    assert {k["chunk_overlap"] for k in seen} == {arms.OVERLAPS[chunk]}
    assert {k["expand_window"] for k in seen} == {0}
    assert {k["collection"] for k in seen} == {ctx.collection}


def test_one_unassembled_search_per_question_and_its_list_in_retrieval(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    assert _run(ctx) == 0
    assert sorted(t for t, _ in engine.searches) == [f"question {i}?" for i in range(4)]
    for _, kwargs in engine.searches:
        assert (kwargs["top_k"], kwargs["fetch_k"], kwargs["unassembled"]) == (100, 100, True)
    retrieval = _lines(ctx.run_dir / "retrieval.jsonl")
    assert [r["qid"] for r in retrieval] == ["q0", "q1", "q2", "q3"]
    assert all(len(r["chunks"]) == 100 for r in retrieval)
    assert "text" not in retrieval[0]["chunks"][0]


def test_evidence_holds_the_head_of_the_saved_list_with_neighbours_merged(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    assert _run(ctx) == 0
    answers = {r["qid"]: r for r in _lines(ctx.run_dir / "answer.jsonl")}
    head = [c["chunk_id"] for c in _lines(ctx.run_dir / "retrieval.jsonl")[0]["chunks"][:10]]
    evidence = answers["q0"]["evidence"]
    assert [i for e in evidence for i in e["chunk_ids"]] == head
    assert evidence[0]["chunk_ids"] == ["ch0", "ch1"]
    assert len(engine.answers[0][1]) == 9


def test_a_t20k_setup_cuts_by_tokens_and_keeps_the_crossing_chunk_apart(tmp_path: Path) -> None:
    engine = Engine(words=300)
    engine.neighbours.update({67: ("s67", 0), 68: ("s67", 1)})
    ctx = _ctx(tmp_path, engine, T20K)
    assert _run(ctx) == 0
    row = _lines(ctx.run_dir / "answer.jsonl")[0]
    assert row["cut_tokens"] == 20_480
    last = row["evidence"][-1]
    assert last["truncated"] is True and last["chunk_ids"] == ["ch68"]
    assert FakeTokens.count(last["text"]) == 20_480 - 68 * 300
    assert [i for e in row["evidence"] for i in e["chunk_ids"]] == [f"ch{i}" for i in range(69)]
    assert row["evidence_tokens"] == sum(FakeTokens.count(e["text"]) for e in row["evidence"])


def test_c2048_by_ten_sends_ten_chunks_and_c2048_t20k_sends_more(tmp_path: Path) -> None:
    for setup, chunks in (("e4b-c2048-r4b-hon", 10), ("e4b-c2048-r4b-hon-t20k", 100)):
        engine = Engine(words=5)
        ctx = _ctx(tmp_path / setup, engine, setup)
        assert _run(ctx) == 0
        row = _lines(ctx.run_dir / "answer.jsonl")[0]
        assert len([i for e in row["evidence"] for i in e["chunk_ids"]]) == chunks
        assert row["cut_tokens"] == chunks * 5


def test_rows_and_traces_are_byte_identical_at_concurrency_8_and_1(tmp_path: Path) -> None:
    files = {}
    for limit in (8, 1):
        ctx = _ctx(tmp_path / str(limit), Engine(), args={"answer_concurrency": limit})
        assert _run(ctx) == 0
        files[limit] = [
            (ctx.run_dir / name).read_bytes()
            for name in ("answer.jsonl", "retrieval.jsonl", "traces.jsonl")
        ]
    assert files[8] == files[1]


def test_a_failed_search_keeps_the_question_pending_and_sends_no_answer(tmp_path: Path) -> None:
    engine = Engine()
    engine.fail_search.add("question 2?")
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    assert "question 2?" not in [t for t, _ in engine.answers]
    ctx = _ctx(tmp_path, engine, resume=True)
    assert [r["qid"] for r in _lines(ctx.run_dir / "answer.jsonl")] == ["q0", "q1"]
    engine.fail_search.clear()
    assert _run(ctx) == 0
    assert [r["qid"] for r in _lines(ctx.run_dir / "retrieval.jsonl")] == ["q0", "q1", "q2", "q3"]


def test_an_unreranked_answer_query_stops_and_answers_nothing_from_it(tmp_path: Path) -> None:
    engine = Engine()
    engine.unranked.add("question 0?")
    with pytest.raises(stagekit35.RerankFailed):
        _run(_ctx(tmp_path, engine, args={"answer_concurrency": 1}))
    assert engine.answers == []
    assert not (_ctx(tmp_path, engine, resume=True).run_dir / ".done-answer.json").exists()


# --- rate limits and the resend rule (task 4.3, section 12) ------------------------------


def test_two_rate_limits_then_success_give_one_row(tmp_path: Path) -> None:
    engine = Engine(script={"question 1?": ["limited", "limited", "ok"]})
    ctx = _ctx(tmp_path, engine)
    assert _run(ctx) == 0
    rows = _lines(ctx.run_dir / "answer.jsonl")
    assert [r["qid"] for r in rows] == ["q0", "q1", "q2", "q3"]
    assert [t for t, _ in engine.answers].count("question 1?") == 3


def test_always_rate_limited_saves_no_row_and_resume_resends_only_open_items(
    tmp_path: Path,
) -> None:
    engine = Engine(script={"question 1?": ["limited"] * 6})
    with pytest.raises(RateLimitStop):
        _run(_ctx(tmp_path, engine, args={"answer_concurrency": 1}))
    ctx = _ctx(tmp_path, engine, resume=True)
    assert [r["qid"] for r in _lines(ctx.run_dir / "answer.jsonl")] == ["q0"]
    assert not (ctx.run_dir / ".done-answer.json").exists()
    engine.answers.clear()
    assert _run(ctx) == 0
    assert sorted(t for t, _ in engine.answers) == ["question 1?", "question 2?", "question 3?"]


def test_an_error_result_is_resent_and_closes_missing_after_three(tmp_path: Path) -> None:
    engine = Engine(script={"question 2?": ["error", "error", "error"]})
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    ctx = _ctx(tmp_path, engine, resume=True)
    assert "q2" not in [r["qid"] for r in _lines(ctx.run_dir / "answer.jsonl")]
    with pytest.raises(stages35.StageIncomplete):
        _run(ctx)
    assert _run(_ctx(tmp_path, engine, resume=True)) == 0
    rows = _lines(ctx.run_dir / "answer.jsonl")
    assert rows[2] == {"qid": "q2", "missing": True, "error": "Generation failed: timeout"}
    marker = json.loads((ctx.run_dir / ".done-answer.json").read_text(encoding="utf-8"))
    assert marker["resent_calls"] == 2 and marker["closed_missing"] == ["q2"]
    assert [r["qid"] for r in _lines(ctx.run_dir / "retrieval.jsonl")] == ["q0", "q1", "q3"]


@pytest.mark.parametrize("step", ["refusal", "empty"])
def test_a_refusal_or_empty_answer_is_final(tmp_path: Path, step: str) -> None:
    engine = Engine(script={"question 0?": [step]})
    ctx = _ctx(tmp_path, engine)
    assert _run(ctx) == 0
    assert [t for t, _ in engine.answers].count("question 0?") == 1
    first = _lines(ctx.run_dir / "answer.jsonl")[0]
    assert first["answer"] == ("" if step == "empty" else "I cannot answer.")


# --- evidence measures (task 14.2) and the selection refusal (task 14.3) -----------------


def test_each_row_records_omrs_fit_measures(tmp_path: Path) -> None:
    from omrs.core.answer.evidence import _labelled_nodes
    from omrs.core.answer.synthesis import _fit_and_measure

    engine = Engine(words=12_000)
    ctx_args = {"answer_concurrency": 1}
    ctx = _ctx(tmp_path, engine, args=ctx_args)
    assert _run(ctx) == 0
    row = _lines(ctx.run_dir / "answer.jsonl")[0]
    nodes = _labelled_nodes(prepare_evidence(engine.answers[0][1]))
    fitted, total = _fit_and_measure(nodes, 131072, 2048, 1)
    marker = "\n[evidence truncated]\n"
    shown = total - 2 * len(marker)
    assert row["evidence_chars"] == sum(len(n.get_content()) + 1 for n in nodes)
    assert row["chars_dropped"] == row["evidence_chars"] - shown > 0
    assert row["truncated_passages"] >= len(nodes) - len(fitted) > 0
    assert row["completion_calls"] == 1
    assert len(row["evidence"]) == len(engine.answers[0][1])


def test_the_answer_stage_refuses_without_selection_json(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    (ctx.layout.root / "selection.json").unlink()
    with pytest.raises(stages35.StageOrderError, match="selection.json is missing"):
        _run(ctx)
    _select(ctx, embedder="8b")
    with pytest.raises(stages35.StageOrderError, match="not an answer setup"):
        _run(ctx)
    assert engine.searches == []
    ctx.args.prefreeze = True
    assert _run(ctx) == 0


def test_each_row_records_the_returned_provider_and_model(tmp_path: Path) -> None:
    # Task 15.9: OMRS reports the serving host and the model the reply names
    # (``sampling.chat.host`` and ``sampling.chat.model_returned``).
    ctx = _ctx(tmp_path, Engine())
    assert _run(ctx) == 0
    row = _lines(ctx.run_dir / "answer.jsonl")[0]
    assert row["provider_returned"] == "h1"
    assert row["model_returned"] == "deepseek/deepseek-v4.1-flash-1017"
