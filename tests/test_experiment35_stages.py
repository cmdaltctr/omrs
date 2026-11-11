"""Experiment 35 stage functions with stub search, answer and judge (no Engine, no router).

Rules under test: a failed question or file keeps its row and its trace row;
``--resume`` skips done work and refuses a run with other inputs; the answer
stage records text, citations, tokens and cost; every claim gets a verdict per
judge with its call record; the determinism stage reports a difference.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.trace import TraceWriter
from tests._exp35_fixtures import load

from omrs.core.answer.judges.base import JudgeCall, Judgement, JudgeUnavailable
from omrs.core.answer.verify import verify_claims

arms = load("arms")
datasets35 = load("datasets35")
outputs35 = load("outputs35")
stages35 = load("stages35")

Q = datasets35.Question


def _questions() -> list[Any]:
    return [
        Q("q1", "first?", ("1001",), "ref one"),
        Q("q2", "second?", ("1002",), "ref two"),
        Q("q3", "third?", ("1003",), "ref three"),
    ]


def _ctx(tmp_path: Path, *, run: int = 1, resume: bool = False, limit: int | None = 3) -> Any:
    layout = outputs35.Layout(tmp_path / "out")
    arm = arms.ARMS[arms.BASELINE]
    questions = _questions()
    key = outputs35.run_key(limit, None, 20261101, [q.qid for q in questions])
    trace = TraceWriter(
        layout.run_dir("bioasq", arm.name, run) / "traces.jsonl",
        benchmark_revision="test",
        run_id=f"bioasq/{arm.name}/run{run}",
        arm=arm.name,
        repetition=run,
        effective_settings={"arm": arm.name},
        model_identities={},
    )
    return stages35.Ctx("bioasq", arm, run, questions, layout, key, resume, trace)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _search_stub(calls: list[str], fail: str = "") -> Any:
    def search(text: str) -> list[dict[str, Any]]:
        calls.append(text)
        if text == fail:
            raise RuntimeError("store unreachable")
        number = text.split("?")[0]
        gold = {"first": "1001", "second": "1999", "third": "1003"}[number]
        return [
            {"chunk_id": f"c-{gold}", "source": f"/c/{gold}.txt", "score": 0.9},
            {"chunk_id": "c-5", "source": "/c/5.txt", "score": 0.1},
        ]

    return search


# --- search ------------------------------------------------------------------------------


def test_search_writes_ids_scores_and_metrics_per_question(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    summary = stages35.search_stage(ctx, _search_stub([]), {})
    rows = _rows(ctx.layout.run_dir("bioasq", ctx.arm.name, 1) / "search.jsonl")
    assert [r["qid"] for r in rows] == ["q1", "q2", "q3"]
    assert rows[0]["ranked_ids"] == ["c-1001", "c-5"]
    assert rows[0]["results"][0]["score"] == 0.9
    assert rows[0]["metrics"]["recall_at_10"] == 1.0
    assert summary["recall_at_10"] == pytest.approx(2 / 3)


def test_a_failed_question_keeps_its_row_and_trace_and_stays_in_the_denominator(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    summary = stages35.search_stage(ctx, _search_stub([], fail="second?"), {})
    run_dir = ctx.layout.run_dir("bioasq", ctx.arm.name, 1)
    rows = {r["qid"]: r for r in _rows(run_dir / "search.jsonl")}
    assert rows["q2"]["failed"] is True
    assert "store unreachable" in rows["q2"]["error"]
    assert summary["n"] == 3
    assert summary["failed"] == 1
    traces = {r["question_id"]: r for r in _rows(run_dir / "traces.jsonl")}
    assert traces["q2"]["status"] == "error"
    assert traces["q1"]["retrieved"]["ids"] == ["c-1001", "c-5"]


def test_resume_skips_a_finished_stage_without_calling_search(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stages35.search_stage(_ctx(tmp_path), _search_stub([]), {})
    capsys.readouterr()
    calls: list[str] = []
    stages35.search_stage(_ctx(tmp_path, resume=True), _search_stub(calls), {})
    assert calls == []
    assert capsys.readouterr().out.strip().endswith("done earlier, skipped")


def test_resume_continues_a_stopped_stage_with_the_missing_questions_only(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    stages35.search_stage(ctx, _search_stub([]), {})
    run_dir = ctx.layout.run_dir("bioasq", ctx.arm.name, 1)
    (run_dir / ".done-search.json").unlink()
    lines = (run_dir / "search.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    # A killed run: one row kept, the second half-written.
    (run_dir / "search.jsonl").write_text(lines[0] + lines[1][:15], encoding="utf-8")
    calls: list[str] = []
    stages35.search_stage(_ctx(tmp_path, resume=True), _search_stub(calls), {})
    assert calls == ["second?", "third?"]
    assert [r["qid"] for r in _rows(run_dir / "search.jsonl")] == ["q1", "q2", "q3"]


def test_a_stage_file_without_resume_is_refused(tmp_path: Path) -> None:
    stages35.search_stage(_ctx(tmp_path), _search_stub([]), {})
    with pytest.raises(outputs35.StageFileExistsError, match="--resume"):
        stages35.search_stage(_ctx(tmp_path), _search_stub([]), {})


def test_resume_with_another_limit_is_refused(tmp_path: Path) -> None:
    stages35.search_stage(_ctx(tmp_path, limit=3), _search_stub([]), {})
    with pytest.raises(outputs35.ResumeMismatchError, match="limit"):
        stages35.search_stage(_ctx(tmp_path, resume=True, limit=None), _search_stub([]), {})


# --- ingest ------------------------------------------------------------------------------


def test_a_failed_file_keeps_its_row_and_the_others_still_ingest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    files = [tmp_path / f"{n}.txt" for n in ("a", "b", "c")]

    async def ingest(path: Path) -> dict[str, Any]:
        if path.name == "b.txt":
            raise OSError("disk full")
        if path.name == "c.txt":
            return {"status": "error", "message": "unsupported"}
        return {"status": "success", "chunks_created": 2, "files_indexed": 1}

    summary = asyncio.run(stages35.ingest_stage(ctx, files, ingest))
    rows = _rows(ctx.layout.index_dir("bioasq", ctx.arm.name) / "ingest.jsonl")
    assert [r["status"] for r in rows] == ["ok", "error", "error"]
    assert summary == {"files": 3, "failed": 2, "chunks_created": 2}


# --- answers and judges ------------------------------------------------------------------


def _answer_stub(calls: list[str]) -> Any:
    async def answer(text: str) -> dict[str, Any]:
        calls.append(text)
        if text == "third?":
            raise TimeoutError("host timed out")
        return {
            "status": "grounded",
            "answer": f"Claim A about {text.rstrip('?')} [1]. Claim B [2].",
            "citations": [{"ordinal": 1}, {"ordinal": 2}],
            "evidence": [
                {"ordinal": 1, "text": "evidence one", "chunk_id": "c1", "source": "/c/1.txt"},
                {"ordinal": 2, "text": "evidence two", "chunk_id": "c2", "source": "/c/2.txt"},
            ],
            "usage": {"input_tokens": 120, "output_tokens": 30, "cost_usd": 0.0004},
            "sampling": {
                "chat": {
                    "temperature": 0.0,
                    "seed": 20261101,
                    "host": "DeepInfra",
                    "host_in_list": True,
                }
            },
        }

    return answer


class _Judge:
    name = "clef_flash"
    version = "clef-flash-claim/1"

    def __init__(self) -> None:
        self.claims: list[str] = []

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        self.claims.append(claim)
        verdict = "supported" if "Claim A" in claim else "unsupported"
        call = JudgeCall(
            strategy=self.name,
            model="ggml-org/Clef-Flash-GGUF:Q8_0",
            host=None,
            sha256="b" * 64,
            version=self.version,
            settings={"threshold": 0.5},
            p_yes=0.9 if verdict == "supported" else 0.1,
        )
        return Judgement(verdict, call)


def test_answer_stage_records_text_citations_tokens_cost_and_host(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    asyncio.run(stages35.answer_stage(ctx, _answer_stub([])))
    rows = {
        r["qid"]: r for r in _rows(ctx.layout.run_dir("bioasq", ctx.arm.name, 1) / "answer.jsonl")
    }
    first = rows["q1"]
    assert first["answer"].startswith("Claim A about first")
    assert first["citations"] == [{"ordinal": 1}, {"ordinal": 2}]
    assert first["evidence"][0]["text"] == "evidence one"
    assert (first["input_tokens"], first["output_tokens"], first["cost_usd"]) == (120, 30, 0.0004)
    assert (first["host"], first["host_in_list"], first["seed"]) == ("DeepInfra", True, 20261101)
    assert rows["q3"]["error"].startswith("TimeoutError")
    assert len(rows) == 3


def test_every_claim_gets_a_verdict_and_call_record_and_failed_answers_keep_a_row(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    asyncio.run(stages35.answer_stage(ctx, _answer_stub([])))
    judge = _Judge()
    asyncio.run(stages35.judge_stage(ctx, "clef_flash", judge, verify_claims))
    path = ctx.layout.run_dir("bioasq", ctx.arm.name, 1) / "judge-clef_flash.jsonl"
    rows = {r["qid"]: r for r in _rows(path)}
    assert [v["verdict"] for v in rows["q1"]["verdicts"]] == ["supported", "unsupported"]
    call = rows["q1"]["verdicts"][0]["call"]
    assert (call["strategy"], call["sha256"], call["version"]) == (
        "clef_flash",
        "b" * 64,
        "clef-flash-claim/1",
    )
    assert rows["q1"]["verdicts"][1]["ordinals"] == [2]
    assert rows["q3"]["error"] == "no answer to judge"
    assert rows["q3"]["verdicts"] == []
    assert len(judge.claims) == 4


def test_a_judge_that_cannot_start_stops_the_stage_before_more_rows(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    asyncio.run(stages35.answer_stage(ctx, _answer_stub([])))

    class Refusing(_Judge):
        async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
            raise JudgeUnavailable("judge model is not Q8_0")

    with pytest.raises(JudgeUnavailable):
        asyncio.run(stages35.judge_stage(ctx, "clef_flash", Refusing(), verify_claims))
    assert not (
        ctx.layout.run_dir("bioasq", ctx.arm.name, 1) / ".done-judge-clef_flash.json"
    ).exists()


def test_a_failed_main_checker_call_stops_the_stage_and_resume_retries_that_answer(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    asyncio.run(stages35.answer_stage(ctx, _answer_stub([])))
    run_dir = ctx.layout.run_dir("bioasq", ctx.arm.name, 1)

    class Failing(_Judge):
        name = "chat"

        async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
            if "second" in claim:
                raise TimeoutError("z.ai timed out")
            return await super().judge(claim, evidence_texts)

    with pytest.raises(JudgeUnavailable, match="TimeoutError"):
        asyncio.run(stages35.judge_stage(ctx, "chat", Failing(), verify_claims))
    assert not (run_dir / ".done-judge-chat.json").exists()
    assert "q2" not in {r["qid"] for r in _rows(run_dir / "judge-chat.jsonl")}

    resumed = _ctx(tmp_path, resume=True)
    asyncio.run(stages35.judge_stage(resumed, "chat", _Judge(), verify_claims))
    rows = {r["qid"]: r for r in _rows(run_dir / "judge-chat.jsonl")}
    assert rows["q2"]["error"] is None
    assert rows["q2"]["verdicts"]


# --- determinism -------------------------------------------------------------------------


def _two_runs(tmp_path: Path, second: Any) -> Any:
    stages35.search_stage(_ctx(tmp_path, run=1), _search_stub([]), {})
    stages35.search_stage(_ctx(tmp_path, run=2), second, {})
    return stages35.determinism_stage(outputs35.Layout(tmp_path / "out"), "bioasq", arms.BASELINE)


def test_identical_runs_pass_the_determinism_check(tmp_path: Path) -> None:
    report = _two_runs(tmp_path, _search_stub([]))
    assert report["retrieval"]["ok"] is True
    assert report["runs"] == [1, 2]


def test_a_changed_ranking_is_reported_with_its_first_differing_rank(tmp_path: Path) -> None:
    def swapped(text: str) -> list[dict[str, Any]]:
        rows = _search_stub([])(text)
        return list(reversed(rows)) if text == "third?" else rows

    report = _two_runs(tmp_path, swapped)
    assert report["retrieval"]["ok"] is False
    assert report["retrieval"]["mismatches"] == [
        {
            "question_id": "q3",
            "first_differing_rank": 1,
            "differing_runs": [2],
            "missing_in_runs": [],
        }
    ]
    written = json.loads(
        (
            outputs35.Layout(tmp_path / "out").arm_dir("bioasq", arms.BASELINE) / "determinism.json"
        ).read_text()
    )
    assert written["retrieval"]["questions_differing"] == 1


def test_changed_verdicts_between_runs_are_reported_per_judge(tmp_path: Path) -> None:
    for run, flip in ((1, False), (2, True)):
        ctx = _ctx(tmp_path, run=run)
        stages35.search_stage(ctx, _search_stub([]), {})
        asyncio.run(stages35.answer_stage(ctx, _answer_stub([])))

        class Flipping(_Judge):
            flips = flip

            async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
                result = await super().judge(claim, evidence_texts)
                if self.flips and "second" in claim:
                    return Judgement("unsupported", result.call)
                return result

        asyncio.run(stages35.judge_stage(ctx, "clef_flash", Flipping(), verify_claims))
    report = stages35.determinism_stage(outputs35.Layout(tmp_path / "out"), "bioasq", arms.BASELINE)
    assert report["retrieval"]["ok"] is True
    assert report["verdicts"]["clef_flash"]["questions_differing"] == 1
    assert report["answers"]["ok"] is True


def test_determinism_needs_two_runs(tmp_path: Path) -> None:
    stages35.search_stage(_ctx(tmp_path, run=1), _search_stub([]), {})
    with pytest.raises(ValueError, match="two runs"):
        stages35.determinism_stage(outputs35.Layout(tmp_path / "out"), "bioasq", arms.BASELINE)
