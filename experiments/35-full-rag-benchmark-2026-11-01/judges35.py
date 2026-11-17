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
  Clef-Flash call record with ``error`` set. Each verdict and each error is
  saved per claim in ``judge-<name>.claims.jsonl`` (review R2-06), so
  ``--resume`` sends only the open claims and never a judged one. The cap of
  3 errors counts per claim call; it closes that claim only. An answer with a
  closed claim keeps its other verdicts and is saved with ``missing: true``
  and ``closed_claims``, so the join counts it as unjudged. A ``chat``
  failure that leaves a claim open stops the stage with exit code 4 once the
  calls in flight have finished (:class:`ClaimCallStop`).
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
from experiments._lib.ordered_rows import ERROR_CAP, OrderedRows, append_line, read_lines

from omrs.core.answer.judges.base import JudgeUnavailable
from omrs.core.answer.verify import split_claims

say = outputs35.say
NO_TEXT = "no answer text"


class ClaimCallStop(RuntimeError):
    """A ``chat`` claim call failed and its claim is still open (exit code 4, review R2-08)."""

    def __init__(self, qid: str, index: int, error: str) -> None:
        """Name the failed call: the answer, the claim and the error."""
        super().__init__(
            f"claim judge call failed on {qid} claim {index}: {error}; the calls in flight "
            "finished. Run the same command again with --resume: it sends only the open claims."
        )


def _limit(ctx: stages35.Ctx, name: str) -> int:
    return ctx.args.chat_concurrency if name == arms.MAIN_JUDGE else 1


def _sender(ctx: stages35.Ctx, name: str) -> Callable[[Callable[[], Awaitable[Any]]], Awaitable]:
    if name == arms.MAIN_JUDGE:
        gate = HostedGate(name, _limit(ctx, name), attempts=ctx.args.rate_limit_attempts)
        return gate.call

    async def plain(send: Callable[[], Awaitable[Any]]) -> Any:
        return await send()

    return plain


class _Claims:
    """The per-claim verdicts and errors of one judge, kept in ``<stage>.claims.jsonl``."""

    def __init__(self, path: Any) -> None:
        self.path = path
        self.saved: dict[tuple[str, int], dict] = {}
        self.errors: dict[tuple[str, int], list[str]] = {}
        for line in read_lines(path):
            key = (str(line["id"]), int(line["index"]))
            if "error" in line:
                self.errors.setdefault(key, []).append(str(line["error"]))
            else:
                self.saved[key] = line["record"]

    def keep(self, qid: str, record: dict) -> None:
        append_line(self.path, {"id": qid, "index": record["index"], "record": record})
        self.saved[(qid, record["index"])] = record

    def fail(self, qid: str, index: int, error: str) -> int:
        append_line(self.path, {"id": qid, "index": index, "error": error})
        self.errors.setdefault((qid, index), []).append(error)
        return len(self.errors[(qid, index)])


def _closed(index: int, ordinals: Any, error: str) -> dict[str, Any]:
    return {"index": index, "ordinals": list(ordinals), "verdict": None, "call": None,
            "error": error, "closed": True}  # fmt: skip


async def _verdicts(
    ctx: stages35.Ctx, qid: str, answer: Mapping[str, Any], parts: tuple
) -> tuple[list[dict], list[tuple[int, str]], list[int]]:
    """Judge the open claims of one answer; return (verdicts, open errors, closed claims)."""
    judge, send, claims, kept = parts
    evidence = answer.get("evidence") or []
    by_ordinal = {e.get("ordinal"): e for e in evidence}
    found, failed, closed = [], [], []
    for index, (claim, ordinals) in enumerate(split_claims(answer["answer"], len(evidence))):
        errors = claims.errors.get((qid, index), [])
        if (qid, index) in claims.saved or len(errors) >= ERROR_CAP:
            found.append(claims.saved.get((qid, index)) or _closed(index, ordinals, errors[-1]))
            closed += [] if (qid, index) in claims.saved else [index]
            continue
        texts = tuple(str(by_ordinal.get(o, {}).get("text") or "") for o in ordinals)
        kept.dispatch(f"{qid}#{index}")
        try:
            judgement = await send(lambda c=claim, t=texts: judge.judge(c, t))
            call = judgement.call
            error = f"call error: {call.error}" if call is not None and call.error else None
        except (RateLimitStop, JudgeUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001 - a failed call is not a verdict
            error = stages35._error(ctx, exc)
        if error is None:
            record = {"index": index, "ordinals": list(ordinals), "verdict": judgement.verdict,
                      "call": call.as_dict() if call is not None else None}  # fmt: skip
            claims.keep(qid, record)
            found.append(record)
        elif claims.fail(qid, index, error) >= ERROR_CAP:
            found.append(_closed(index, ordinals, error))
            closed.append(index)
        else:
            failed.append((index, error))
    return found, failed, closed


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
    found = [v for r in rows for v in r.get("verdicts", [])]
    verdicts = Counter(v["verdict"] for v in found if not v.get("closed"))
    return {
        "answers": len(ctx.questions),
        "rows": len(rows),
        "claims": sum(verdicts.values()),
        "verdicts": dict(sorted(verdicts.items())),
        "closed_claims": sum(1 for v in found if v.get("closed")),
        "not_judged": sum(1 for r in rows if r.get("not_judged")),
        "missing": sum(1 for r in rows if r.get("missing")),
        "resent_calls": kept.resent_calls,
        "closed_missing": [r["qid"] for r in rows if r.get("closed_claims")],
    }


async def judge_one(ctx: stages35.Ctx, name: str, answers: Mapping[str, Mapping]) -> None:
    """Judge every open answer of the run folder with judge *name*.

    Raises:
        JudgeUnavailable: The judge cannot start (exit code 4).
        ClaimCallStop: A ``chat`` claim call failed and its claim is still
            open (exit code 4, after the calls in flight).
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
        parts = (
            ctx.judge(name),
            _sender(ctx, name),
            _Claims(ctx.run_dir / f"{stage}.claims.jsonl"),
        )

        async def one(qid: str) -> None:
            answer = answers.get(qid) or {"missing": True}
            started = stagekit35.clock()
            if answer.get("missing") or not answer.get("answer"):
                row = _row(qid, name, [], 0.0, NO_TEXT)
                kept.submit(qid, row, _trace(ctx, name, qid, row, None))
                return
            verdicts, failed, closed = await _verdicts(ctx, qid, answer, (*parts, kept))
            for index, error in failed:
                say(f"[{stage}] {qid} claim {index}: ERROR {error}")
            if failed and name == arms.MAIN_JUDGE:
                raise ClaimCallStop(qid, *failed[0])
            if failed:
                return  # open claims stay pending; --resume sends only them
            row = _row(qid, name, verdicts, round(stagekit35.clock() - started, 3), None)
            error = None
            if closed:
                row.update(missing=True, closed_claims=closed)
                error = f"claims {closed} closed after {ERROR_CAP} errors"
            kept.submit(qid, row, _trace(ctx, name, qid, row, error))

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
