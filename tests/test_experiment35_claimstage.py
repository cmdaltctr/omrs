"""Experiment 35 claim-kinds stage wrapper, ``claimstage35.py`` (tasks 8.5, 16.29; section 12).

The stage runs A6's classifier through the hosted gate with the resend rule
and also sorts the uncited segments of each answer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests._exp35_fixtures import load, open_half_b

claimstage35 = load("claimstage35")
claimkinds35 = load("claimkinds35")
outputs35 = load("outputs35")
stages35 = load("stages35")

ANSWER = "Fact one [1]. Uncited fact."


class RateLimited(Exception):
    status_code = 429


def _ctx(tmp_path: Path, classifier, *, resume: bool = False, concurrency: int = 16):
    run_dir = tmp_path / "bioasq" / "answer" / "e4b-c512-roff-hoff" / "run1"
    if not (run_dir / "answer.jsonl").exists():
        run_dir.mkdir(parents=True)
        rows = [
            {"qid": q, "answer": ANSWER, "evidence": [{"ordinal": 1, "text": "t"}]}
            for q in ("q1", "q2")
        ]
        (run_dir / "answer.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (run_dir / ".done-answer.json").write_text("{}")
    args = SimpleNamespace(
        classify_concurrency=concurrency, rate_limit_attempts=1, prefreeze=False, smoke=False
    )
    open_half_b(tmp_path)
    questions = [SimpleNamespace(qid=q, text=f"question {q}") for q in ("q1", "q2")]
    return SimpleNamespace(
        layout=outputs35.Layout(tmp_path),
        run_dir=run_dir,
        questions=questions,
        key={"seed": 1},
        resume=resume,
        args=args,
        classifier=classifier,
        classifier_version="v1",
    )


def _reply(text: str = "factual") -> SimpleNamespace:
    return SimpleNamespace(text=text, model_returned="openai/gpt-oss-120b", provider_returned="x")


def _rows(ctx) -> list[dict]:
    return outputs35.read_rows(ctx.run_dir / "claim-kinds.jsonl")


async def _no_wait(_: float) -> None:
    return None


def _run(ctx) -> int:
    return asyncio.run(claimstage35.claimkinds_stage(ctx, sleep=_no_wait))


def test_classifies_claims_and_uncited_segments_from_question_and_text_only(tmp_path) -> None:
    seen: list[list[dict]] = []

    async def classifier(messages):
        seen.append(messages)
        return _reply()

    ctx = _ctx(tmp_path, classifier)
    assert _run(ctx) == 0
    rows = _rows(ctx)
    assert [(r["qid"], r["uncited"]) for r in rows] == [
        ("q1", False),
        ("q1", True),
        ("q2", False),
        ("q2", True),
    ]
    assert rows[0]["claim_key"] == claimkinds35.claim_key("q1", "Fact one.")
    assert rows[1]["claim_key"] == claimkinds35.claim_key("q1", "Uncited fact.")
    assert all(r["kind"] == "factual" and r["version"] == "v1" for r in rows)
    assert rows[0]["model_returned"] == "openai/gpt-oss-120b"
    user = [m["content"] for m in seen[0] if m["role"] == "user"][0]
    assert user == "Question: question q1\nSentence: Fact one."
    marker = json.loads((ctx.run_dir / ".done-claimkinds.json").read_text())
    assert marker["kinds"] == {"factual": 4}


def test_resume_skips_saved_claims(tmp_path) -> None:
    calls = []

    async def classifier(messages):
        calls.append(messages)
        return _reply()

    assert _run(_ctx(tmp_path, classifier)) == 0
    (
        tmp_path / "bioasq" / "answer" / "e4b-c512-roff-hoff" / "run1" / ".done-claimkinds.json"
    ).unlink()
    assert _run(_ctx(tmp_path, classifier, resume=True)) == 0
    assert len(calls) == 4


def test_a_429_on_every_attempt_saves_no_kind_and_exits_5(tmp_path) -> None:
    async def classifier(messages):
        raise RateLimited("slow down")

    ctx = _ctx(tmp_path, classifier)
    assert _run(ctx) == claimstage35.EXIT_RATE_LIMIT == 5
    assert _rows(ctx) == []
    assert not (ctx.run_dir / ".done-claimkinds.json").exists()


def test_an_error_is_resent_and_the_third_closes_it_as_unclassified(tmp_path) -> None:
    async def failing(messages):
        if "Fact one" in messages[-1]["content"] and "q1" in messages[-1]["content"]:
            raise RuntimeError("boom")
        return _reply()

    ctx = _ctx(tmp_path, failing)
    with pytest.raises(claimstage35.StageIncomplete):
        _run(ctx)
    assert len(_rows(ctx)) == 0  # the open first item holds back the rows after it
    for _ in range(2):
        ctx = _ctx(tmp_path, failing, resume=True)
        try:
            _run(ctx)
        except claimstage35.StageIncomplete:
            pass
    rows = _rows(ctx)
    assert rows[0]["missing"] is True and rows[0]["kind"] is None
    assert rows[0]["claim_key"] == claimkinds35.claim_key("q1", "Fact one.")
    assert len(rows) == 4
    assert (ctx.run_dir / ".done-claimkinds.json").exists()


def test_an_unreadable_reply_is_saved_as_unreadable(tmp_path) -> None:
    async def classifier(messages):
        return _reply("I am not sure")

    ctx = _ctx(tmp_path, classifier)
    assert _run(ctx) == 0
    assert {r["kind"] for r in _rows(ctx)} == {"unreadable"}


def test_never_more_calls_in_flight_than_the_concurrency(tmp_path) -> None:
    state = {"now": 0, "peak": 0}

    async def classifier(messages):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return _reply()

    assert _run(_ctx(tmp_path, classifier, concurrency=2)) == 0
    assert state["peak"] == 2


def test_an_uncited_segment_with_a_claim_text_keeps_its_own_item(tmp_path) -> None:
    async def classifier(messages):
        return _reply()

    ctx = _ctx(tmp_path, classifier)
    rows = [{"qid": "q1", "answer": "Same [1]. Same.", "evidence": [{"ordinal": 1, "text": "t"}]}]
    (ctx.run_dir / "answer.jsonl").write_text(json.dumps(rows[0]) + "\n")
    assert _run(ctx) == 0
    assert [r["uncited"] for r in _rows(ctx)] == [False, True]


def test_add_arguments_takes_the_prompt_examples() -> None:
    parser = argparse.ArgumentParser()
    claimstage35.add_arguments(parser)
    args = parser.parse_args(["--classify-examples", "ex.json"])
    assert args.classify_examples == Path("ex.json")


def test_refuses_a_run_folder_without_a_finished_answer_stage(tmp_path) -> None:
    async def classifier(messages):
        return _reply()

    ctx = _ctx(tmp_path / "empty", classifier)
    (ctx.run_dir / ".done-answer.json").unlink()
    with pytest.raises(stages35.StageOrderError, match=str(ctx.run_dir)):
        _run(ctx)
    assert not (ctx.run_dir / ".done-claimkinds.json").exists()
