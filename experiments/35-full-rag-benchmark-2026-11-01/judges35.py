"""Experiment 35 claim judge stage (task 4.4; pre-registration sections 6, 11 and 12).

``--stage judge --judges chat,clef_flash`` judges every cited claim of every
saved answer of one run folder with each named judge, one row per answer in
``judge-<name>.jsonl``. ``--answers closedbook-own``, ``closedbook-rag`` or
``oracle`` judges those folders instead of the answer folder.

* ``chat`` (GLM-5.3, hosted) runs through the hosted gate with at most
  ``--chat-concurrency`` calls in flight. ``clef_flash`` (local) never has
  more than one call in flight.
* Rows reach the file in frozen order, so they are byte-identical at any
  concurrency for a fixed judge and a fixed clock.
* A claim call that fails is never a verdict: a ``chat`` exception, or a
  Clef-Flash call record with ``error`` set. The answer saves no row and is
  sent again on ``--resume``; its third failure closes it as missing. A
  ``chat`` failure that does not close the answer stops the stage with exit
  code 4 once the calls in flight have finished.
* An answer with no text (missing or empty) gets a ``not_judged`` row and
  no call. A ``chat`` rate limit past the attempt limit stops with exit 5.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import arms
import outputs35
import stagekit35
import stages35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows

from omrs.core.answer.judges.base import JudgeUnavailable
from omrs.core.answer.verify import split_claims

say = outputs35.say
NO_TEXT = "no answer text"


class ClaimCallFailed(RuntimeError):
    """A judge call came back with an error record; it is not a verdict."""


def _limit(ctx: stages35.Ctx, name: str) -> int:
    return ctx.args.chat_concurrency if name == arms.MAIN_JUDGE else 1


def _sender(ctx: stages35.Ctx, name: str) -> Callable[[Callable[[], Awaitable[Any]]], Awaitable]:
    if name == arms.MAIN_JUDGE:
        gate = HostedGate(name, _limit(ctx, name), attempts=ctx.args.rate_limit_attempts)
        return gate.call

    async def plain(send: Callable[[], Awaitable[Any]]) -> Any:
        return await send()

    return plain


async def _verdicts(judge: Any, answer: Mapping[str, Any], send: Callable) -> list[dict]:
    evidence = answer.get("evidence") or []
    by_ordinal = {e.get("ordinal"): e for e in evidence}
    found = []
    for index, (claim, ordinals) in enumerate(split_claims(answer["answer"], len(evidence))):
        texts = tuple(str(by_ordinal.get(o, {}).get("text") or "") for o in ordinals)
        judgement = await send(lambda c=claim, t=texts: judge.judge(c, t))
        call = judgement.call
        if call is not None and call.error:
            raise ClaimCallFailed(f"claim {index}: {call.error}")
        found.append(
            {
                "index": index,
                "ordinals": list(ordinals),
                "verdict": judgement.verdict,
                "call": call.as_dict() if call is not None else None,
            }
        )
    return found


def _row(qid: str, name: str, verdicts: list[dict], seconds: float, not_judged: str | None) -> dict:
    calls = [v["call"] for v in verdicts if v.get("call")]
    return {
        "qid": qid,
        "judge": name,
        "verdicts": verdicts,
        # Task 15.9: OMRS's call record names the reply's host, not the model it names.
        "model_returned": [],
        "provider_returned": sorted({c["host"] for c in calls if c.get("host")}),
        "verified": bool(verdicts) and all(v["verdict"] == "supported" for v in verdicts),
        "skipped_reason": None if verdicts or not_judged else "no cited claims",
        "not_judged": not_judged,
        "seconds": seconds,
    }


def _trace(ctx: stages35.Ctx, name: str, qid: str, row: Mapping | None, error: str | None) -> dict:
    calls = [v["call"] for v in (row or {}).get("verdicts", []) if v.get("call")]
    return ctx.trace.row(
        stage=f"judge-{name}",
        dataset=ctx.dataset,
        question_id=qid,
        status="error" if error else ("degraded" if (row or {}).get("not_judged") else "ok"),
        error=error or (row or {}).get("not_judged"),
        durations_s={"judge": row["seconds"]} if row else None,
        answer_model=arms.ANSWER_MODEL,
        judge_model=str(calls[0]["model"]) if calls else name,
    )


def _summary(ctx: stages35.Ctx, rows: list[dict], kept: OrderedRows) -> dict[str, Any]:
    verdicts = Counter(v["verdict"] for r in rows for v in r.get("verdicts", []))
    return {
        "answers": len(ctx.questions),
        "rows": len(rows),
        "claims": sum(verdicts.values()),
        "verdicts": dict(sorted(verdicts.items())),
        "not_judged": sum(1 for r in rows if r.get("not_judged")),
        "missing": sum(1 for r in rows if r.get("missing")),
        "resent_calls": kept.resent_calls,
        "closed_missing": kept.closed_missing,
    }


async def judge_one(ctx: stages35.Ctx, name: str, answers: Mapping[str, Mapping]) -> None:
    """Judge every open answer of the run folder with judge *name*.

    Raises:
        JudgeUnavailable: The judge cannot start, or a ``chat`` call failed
            and the answer is not yet closed (exit code 4).
        RateLimitStop: ``chat`` rate-limited past the attempt limit (exit 5).
        stages35.StageIncomplete: Answers stay open after their errors.
    """
    stage = f"judge-{name}"
    with outputs35.RowFile(ctx.run_dir, stage, ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[{stage}] {ctx.dataset}/{ctx.setup}/run{ctx.run}: done earlier, skipped")
            return
        opened = stagekit35.open_checks(ctx)
        kept = OrderedRows(log, [q.qid for q in ctx.questions], trace=ctx.trace)
        judge = ctx.judge(name)
        send = _sender(ctx, name)

        async def one(qid: str) -> None:
            answer = answers.get(qid) or {"missing": True}
            started = stagekit35.clock()
            if answer.get("missing") or not answer.get("answer"):
                row = _row(qid, name, [], 0.0, NO_TEXT)
                kept.submit(qid, row, _trace(ctx, name, qid, row, None))
                return
            kept.dispatch(qid)
            try:
                verdicts = await _verdicts(judge, answer, send)
            except (RateLimitStop, JudgeUnavailable):
                raise
            except Exception as exc:  # noqa: BLE001 - a failed call is not a verdict
                error = stages35._error(ctx, exc)
                closed = kept.fail(qid, error, _trace(ctx, name, qid, None, error))
                say(f"[{stage}] {qid}: ERROR {error}")
                if name == arms.MAIN_JUDGE and not closed:
                    raise JudgeUnavailable(
                        f"claim judge {name} call failed; run again with --resume"
                    ) from exc
                return
            row = _row(qid, name, verdicts, round(stagekit35.clock() - started, 3), None)
            kept.submit(qid, row, _trace(ctx, name, qid, row, None))

        await stagekit35.drain(kept.todo(), one, _limit(ctx, name))
        summary = _summary(ctx, log.rows(), kept)
        outputs35.write_json(ctx.run_dir / f"{stage}-summary.json", summary)
        checks = stagekit35.close_checks(ctx, opened)
        if not kept.finish({**summary, "checks": checks}):
            raise stages35.StageIncomplete(f"{stage} {ctx.setup}: answers still open")
    say(f"[{stage}] {ctx.dataset}/{ctx.setup}/run{ctx.run}: {summary['claims']} claims")


async def judge_stage(ctx: stages35.Ctx) -> int:
    """Run each ``--judges`` judge over the finished answers of the run folder; return 0.

    Raises:
        stages35.StageOrderError: No finished answer stage, or no judge named.
        scoring35.HalfBLocked: A main run while half B is locked.
    """
    stagekit35.require_half_b_open(ctx)
    if not (ctx.run_dir / ".done-answer.json").exists():
        raise stages35.StageOrderError(
            f"the judge stage needs a finished answer stage in {ctx.run_dir}"
        )
    names = arms.parse_judges(ctx.args.judges)
    if not names:
        raise stages35.StageOrderError("the judge stage needs --judges (chat, clef_flash)")
    answers = {r["qid"]: r for r in outputs35.read_rows(ctx.run_dir / "answer.jsonl")}
    for name in names:
        await judge_one(ctx, name, answers)
    return 0
