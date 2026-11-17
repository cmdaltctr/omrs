"""Experiment 35 claim judge stage (``judges35.py``) with stub judges (task 4.4, section 12).

Rules under test: the in-flight limits of ``chat`` and ``clef_flash``;
byte-identical rows and traces at any concurrency; a ``chat`` rate limit
stops with exit 5 and saves nothing; a ``chat`` failure exits 4 after the
calls in flight, is resent, and closes after its third error; a Clef-Flash
call with an error record is a failed call, never a verdict.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from experiments._lib.hosted_calls import RateLimitStop
from tests._exp35_fixtures import load, stage_ctx

from omrs.core.answer.judges.base import JudgeCall, Judgement, JudgeUnavailable

datasets35 = load("datasets35")
judges35 = load("judges35")
outputs35 = load("outputs35")
stagekit35 = load("stagekit35")
stages35 = load("stages35")

SETUP = "e4b-c1024-r4b-hon"


class Limited(Exception):
    status_code = 429
    response = SimpleNamespace(headers={"retry-after": "0"})


class Judge:
    """Stub judge: a script of outcomes per claim; records the most calls in flight."""

    def __init__(self, name: str, script: dict[str, list[str]] | None = None) -> None:
        self.name = name
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[str] = []
        self.flight = 0
        self.most = 0

    async def judge(self, claim: str, texts: tuple[str, ...]) -> Judgement:
        self.calls.append(claim)
        self.flight += 1
        self.most = max(self.most, self.flight)
        try:
            await asyncio.sleep(0.001 * (len(claim) % 5))
            step = self.script[claim].pop(0) if self.script.get(claim) else "ok"
            if step == "limit":
                raise Limited()
            if step == "fail":
                raise RuntimeError("judge timeout")
            call = JudgeCall(
                self.name, f"{self.name}-model", None, None, "1", {}, None,
                "unreachable" if step == "error" else None,
            )  # fmt: skip
            verdict = "unparseable" if step == "error" else "supported"
            return Judgement(verdict, call)
        finally:
            self.flight -= 1


def _questions(n: int = 6) -> list[Any]:
    return [datasets35.Question(qid=f"q{i}", text=f"question {i}?", relevant=()) for i in range(n)]


def _answers(ctx: Any, n: int = 6, empty: tuple[int, ...] = ()) -> None:
    rows = []
    for i in range(n):
        text = "" if i in empty else f"Claim {i} one [1]. Claim {i} two [1]."
        rows.append({"qid": f"q{i}", "answer": text, "evidence": [{"ordinal": 1, "text": f"e{i}"}]})
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "answer.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    outputs35.write_json(ctx.run_dir / ".done-answer.json", {"rows": n})


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stagekit35, "clock", lambda: 0.0)


def _ctx(tmp_path: Path, judge: Judge, *, chat: int = 4, resume: bool = False, **kw: Any) -> Any:
    ctx = stage_ctx(
        tmp_path,
        "judge",
        SETUP,
        kind="answer",
        questions=_questions(),
        resume=resume,
        args={"judges": judge.name, "chat_concurrency": chat},
        judge=lambda name: judge,
        **kw,
    )
    if not (ctx.run_dir / "answer.jsonl").exists():
        _answers(ctx)
    return ctx


def _run(ctx: Any) -> int:
    return asyncio.run(judges35.judge_stage(ctx))


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_chat_judges_several_answers_at_once_within_the_limit(tmp_path: Path) -> None:
    judge = Judge("chat")
    ctx = _ctx(tmp_path, judge, chat=3)
    assert _run(ctx) == 0
    assert judge.most == 3
    rows = _lines(ctx.run_dir / "judge-chat.jsonl")
    assert [r["qid"] for r in rows] == [f"q{i}" for i in range(6)]
    assert [v["index"] for v in rows[0]["verdicts"]] == [0, 1]


def test_clef_flash_never_has_more_than_one_call_in_flight(tmp_path: Path) -> None:
    judge = Judge("clef_flash")
    assert _run(_ctx(tmp_path, judge, chat=8)) == 0
    assert judge.most == 1


def test_rows_and_traces_are_byte_identical_at_concurrency_4_and_1(tmp_path: Path) -> None:
    found = {}
    for limit in (4, 1):
        ctx = _ctx(tmp_path / str(limit), Judge("chat"), chat=limit)
        assert _run(ctx) == 0
        found[limit] = [
            (ctx.run_dir / n).read_bytes() for n in ("judge-chat.jsonl", "traces.jsonl")
        ]
    assert found[4] == found[1]


def test_a_chat_rate_limit_on_every_attempt_stops_and_saves_no_row(tmp_path: Path) -> None:
    judge = Judge("chat", {"Claim 2 one.": ["limit"] * 6})
    ctx = _ctx(tmp_path, judge, chat=1)
    with pytest.raises(RateLimitStop):
        _run(ctx)
    assert [r["qid"] for r in _lines(ctx.run_dir / "judge-chat.jsonl")] == ["q0", "q1"]
    assert not (ctx.run_dir / ".done-judge-chat.json").exists()


def test_a_chat_failure_exits_4_is_resent_and_closes_after_three(tmp_path: Path) -> None:
    judge = Judge("chat", {"Claim 1 two.": ["fail", "fail", "fail"]})
    for _ in range(2):
        with pytest.raises(JudgeUnavailable):
            _run(_ctx(tmp_path, judge, resume=True))
    ctx = _ctx(tmp_path, judge, resume=True)
    assert "q1" not in [r["qid"] for r in _lines(ctx.run_dir / "judge-chat.jsonl")]
    assert _run(ctx) == 0
    rows = _lines(ctx.run_dir / "judge-chat.jsonl")
    assert rows[1] == {"qid": "q1", "missing": True, "error": "RuntimeError: judge timeout"}
    marker = json.loads((ctx.run_dir / ".done-judge-chat.json").read_text(encoding="utf-8"))
    assert marker["closed_missing"] == ["q1"] and marker["resent_calls"] == 2


def test_a_chat_failure_lets_the_calls_in_flight_finish_first(tmp_path: Path) -> None:
    judge = Judge("chat", {"Claim 0 one.": ["fail"]})
    ctx = _ctx(tmp_path, judge, chat=4)
    with pytest.raises(JudgeUnavailable):
        _run(ctx)
    pending = outputs35.read_rows(ctx.run_dir / "judge-chat.pending.jsonl")
    assert {p["id"] for p in pending} == {"q1", "q2", "q3"}


def test_a_clef_flash_error_record_is_a_failed_call_never_a_verdict(tmp_path: Path) -> None:
    judge = Judge("clef_flash", {"Claim 3 one.": ["error", "error", "error"]})
    for _ in range(2):
        with pytest.raises(stages35.StageIncomplete):
            _run(_ctx(tmp_path, judge, resume=True))
        ctx = _ctx(tmp_path, judge, resume=True)
        rows = _lines(ctx.run_dir / "judge-clef_flash.jsonl")
        assert "q3" not in [r["qid"] for r in rows]
        assert all(v["verdict"] != "unparseable" for r in rows for v in r["verdicts"])
    assert _run(ctx) == 0
    assert _lines(ctx.run_dir / "judge-clef_flash.jsonl")[3]["missing"] is True


def test_an_answer_with_no_text_is_not_judged_and_sends_no_call(tmp_path: Path) -> None:
    judge = Judge("chat")
    ctx = stage_ctx(
        tmp_path, "judge", SETUP, kind="answer", questions=_questions(),
        args={"judges": "chat"}, judge=lambda name: judge,
    )  # fmt: skip
    _answers(ctx, empty=(2,))
    assert _run(ctx) == 0
    row = _lines(ctx.run_dir / "judge-chat.jsonl")[2]
    assert row["not_judged"] == "no answer text" and row["verdicts"] == []
    assert not any(c.startswith("Claim 2") for c in judge.calls)


def test_the_judge_stage_needs_the_finished_answer_stage(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, Judge("chat"))
    (ctx.run_dir / ".done-answer.json").unlink()
    with pytest.raises(stages35.StageOrderError, match="finished answer stage"):
        _run(ctx)


class HostJudge(Judge):
    """A judge whose call records name the serving host, as the GLM-5.3 reply does."""

    async def judge(self, claim: str, texts: tuple[str, ...]) -> Judgement:
        found = await super().judge(claim, texts)
        call = JudgeCall("chat", "glm-5.3", "z-ai", None, "1", {}, None, None)
        return Judgement(found.verdict, call)


def test_chat_rows_record_the_returned_provider_and_model(tmp_path: Path) -> None:
    # Task 15.9: OMRS's judge call record names the host of the reply, not its model.
    ctx = _ctx(tmp_path, HostJudge("chat"))
    assert _run(ctx) == 0
    row = _lines(ctx.run_dir / "judge-chat.jsonl")[0]
    assert row["provider_returned"] == ["z-ai"]
    assert row["model_returned"] == []
