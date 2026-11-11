"""Experiment 35 stages: ingest, search, answer, claim judges and determinism (design D4, D5, D8).

Each stage takes its outside world as plain callables (an ``ingest`` coroutine,
a ``search`` function, an ``answer`` coroutine, a claim judge), so the tests run
on stubs and ``run_arms.py`` passes the real Engine and judges.

Rules every stage keeps:

* one row per item, appended at once; a failed item keeps its row with the
  error, and stays in the denominator of every summary;
* one D8 trace row per item through ``TraceWriter``;
* ``--resume`` skips a finished stage, and inside a stopped stage skips the
  items already written;
* error text goes through ``redact`` before it is written.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import arms
import outputs35
import scoring35
from experiments._lib.determinism import compare_runs
from experiments._lib.ranking import result_id
from experiments._lib.trace import TraceWriter

say = outputs35.say


class StageOrderError(RuntimeError):
    """A stage needs a stage that has not finished."""


def _same(text: str) -> str:
    return text


@dataclass
class Ctx:
    """One dataset, arm and repetition.

    Attributes:
        dataset: The dataset name.
        arm: The arm.
        run: The repetition (1, 2 or 3).
        questions: The selected questions, in frozen order.
        layout: The output layout.
        key: The run key (``outputs35.run_key``).
        resume: Continue a started stage.
        trace: The D8 trace writer of this stage.
        redact: Removes secrets from error text.
    """

    dataset: str
    arm: arms.Arm
    run: int
    questions: list[Any]
    layout: outputs35.Layout
    key: Mapping[str, Any]
    resume: bool
    trace: TraceWriter
    redact: Callable[[str], str] = field(default=_same)

    @property
    def run_dir(self) -> Path:
        """The folder of this repetition."""
        return self.layout.run_dir(self.dataset, self.arm.name, self.run)


def _error(ctx: Ctx, exc: BaseException) -> str:
    return ctx.redact(f"{type(exc).__name__}: {exc}")[:500]


def _status(error: str | None) -> str:
    return "error" if error else "ok"


# --- ingest ------------------------------------------------------------------------------


def _ingest_failure(result: Mapping[str, Any]) -> str:
    """Return why an ingest result failed, or ``""`` (a failed file may return, not raise)."""
    if result.get("status") == "error":
        return f"ingest status error: {result.get('message') or result.get('error_type') or ''}"
    warnings = result.get("warnings")
    return "ingest warnings: " + "; ".join(str(w) for w in warnings) if warnings else ""


async def ingest_stage(
    ctx: Ctx, files: Sequence[Path], ingest: Callable[[Path], Awaitable[Mapping[str, Any]]]
) -> dict[str, Any]:
    """Ingest each file on its own into the arm's index; one row per file."""
    log = outputs35.RowFile(
        ctx.layout.index_dir(ctx.dataset, ctx.arm.index_of), "ingest", ctx.key, resume=ctx.resume
    )
    if log.done:
        say(f"[ingest] {ctx.dataset}/{ctx.arm.index_of}: done earlier, skipped")
        return _ingest_summary(log.rows())
    done = log.done_ids("file")
    for path in files:
        if path.name in done:
            continue
        started = time.perf_counter()
        result: Mapping[str, Any] = {}
        try:
            result = await ingest(path)
            error = ctx.redact(_ingest_failure(result))[:500]
        except Exception as exc:  # noqa: BLE001 - record the file and continue (D8)
            error = _error(ctx, exc)
        seconds = round(time.perf_counter() - started, 3)
        chunks = int(result.get("chunks_created") or 0)
        log.append(
            {
                "file": path.name,
                "status": _status(error),
                "error": error or None,
                "chunks_created": chunks,
                "seconds": seconds,
            }
        )
        ctx.trace.write(
            stage="ingest",
            dataset=ctx.dataset,
            question_id=path.name,
            status=_status(error),
            error=error or None,
            chunk_counts={"created": chunks},
            durations_s={"ingest": seconds},
        )
        say(f"[ingest] {path.name}: {seconds}s" + (f" ERROR {error}" if error else ""))
    summary = _ingest_summary(log.rows())
    log.mark_done(summary)
    return summary


def _ingest_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "files": len(rows),
        "failed": sum(1 for r in rows if r["status"] != "ok"),
        "chunks_created": sum(int(r.get("chunks_created") or 0) for r in rows),
    }


# --- search ------------------------------------------------------------------------------


def _slim(row: Mapping[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata") or {}
    labels = row.get("page_labels") or [row.get("page_label")]
    return {
        "id": result_id(row),
        "source": str(row.get("source") or ""),
        "file_name": meta.get("file_name"),
        "page_labels": [str(label) for label in labels if label is not None],
        "score": row.get("score"),
    }


def search_stage(
    ctx: Ctx, search: Callable[[str], list[dict[str, Any]]], id_map: Mapping[str, str]
) -> dict[str, Any]:
    """Search each question; write retrieved IDs, scores and the primary metrics."""
    log = outputs35.RowFile(ctx.run_dir, "search", ctx.key, resume=ctx.resume)
    if log.done:
        say(f"[search] {ctx.dataset}/{ctx.arm.name}/run{ctx.run}: done earlier, skipped")
        return scoring35.summarise(log.rows())
    done = log.done_ids("qid")
    for question in ctx.questions:
        if question.qid in done:
            continue
        started = time.perf_counter()
        error, results, slim = None, [], []
        try:
            results = search(question.text)
            slim = [_slim(row) for row in results]
        except Exception as exc:  # noqa: BLE001 - a blank result ID fails too; keep the row
            error, results, slim = _error(ctx, exc), [], []
        seconds = round(time.perf_counter() - started, 3)
        units = scoring35.ranked_units(ctx.dataset, question, results, id_map)
        metrics = (
            scoring35.failed_metrics(ctx.dataset)
            if error
            else scoring35.question_metrics(ctx.dataset, question, results, id_map)
        )
        ranked = [item["id"] for item in slim]
        log.append(
            {
                "qid": question.qid,
                "failed": bool(error),
                "error": error,
                "ranked_ids": ranked,
                "units": units,
                "results": slim,
                "metrics": metrics,
                "seconds": seconds,
            }
        )
        ctx.trace.write(
            stage="search",
            dataset=ctx.dataset,
            question_id=question.qid,
            status=_status(error),
            error=error,
            retrieved={"ids": ranked, "units": units, "scores": [item["score"] for item in slim]},
            durations_s={"search": seconds},
        )
        say(f"[search] {question.qid}: {seconds}s" + (f" ERROR {error}" if error else ""))
    summary = scoring35.summarise(log.rows())
    outputs35.write_json(ctx.run_dir / "search-summary.json", summary)
    log.mark_done(summary)
    return summary


# --- answers -----------------------------------------------------------------------------


def _answer_row(qid: str, result: Mapping[str, Any], error: str | None, seconds: float) -> dict:
    usage = result.get("usage") or {}
    chat = (result.get("sampling") or {}).get("chat") or {}
    evidence = [
        {key: item.get(key) for key in ("ordinal", "text", "chunk_id", "source")}
        for item in result.get("evidence") or []
    ]
    return {
        "qid": qid,
        "status": result.get("status"),
        "answer": str(result.get("answer") or ""),
        "citations": list(result.get("citations") or []),
        "evidence": evidence,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "calls": usage.get("calls"),
        "cost_usd": usage.get("cost_usd"),
        "host": chat.get("host"),
        "host_in_list": chat.get("host_in_list"),
        "temperature": chat.get("temperature"),
        "seed": chat.get("seed"),
        "seconds": seconds,
        "error": error,
    }


async def answer_stage(
    ctx: Ctx, answer: Callable[[str], Awaitable[Mapping[str, Any]]]
) -> dict[str, Any]:
    """Answer each question once (claim checks off); record text, citations, tokens and cost."""
    log = outputs35.RowFile(ctx.run_dir, "answer", ctx.key, resume=ctx.resume)
    if log.done:
        say(f"[answer] {ctx.dataset}/{ctx.arm.name}/run{ctx.run}: done earlier, skipped")
        return _answer_summary(log.rows())
    done = log.done_ids("qid")
    for question in ctx.questions:
        if question.qid in done:
            continue
        started = time.perf_counter()
        result: Mapping[str, Any] = {}
        error: str | None = None
        try:
            result = await answer(question.text)
            if result.get("status") == "error":
                error = ctx.redact(str(result.get("error") or "answer status error"))[:500]
        except Exception as exc:  # noqa: BLE001 - keep the row (D8)
            error = _error(ctx, exc)
        row = _answer_row(question.qid, result, error, round(time.perf_counter() - started, 3))
        log.append(row)
        tokens = {k: row[k] for k in ("input_tokens", "output_tokens") if isinstance(row[k], int)}
        ctx.trace.write(
            stage="answer",
            dataset=ctx.dataset,
            question_id=question.qid,
            status=_status(error),
            error=error,
            token_counts=tokens or None,
            durations_s={"answer": row["seconds"]},
            answer_model=arms.ANSWER_MODEL,
        )
        say(f"[answer] {question.qid}: {row['seconds']}s" + (f" ERROR {error}" if error else ""))
    summary = _answer_summary(log.rows())
    outputs35.write_json(ctx.run_dir / "answer-summary.json", summary)
    log.mark_done(summary)
    return summary


def _answer_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def total(name: str) -> float:
        return sum(r[name] for r in rows if isinstance(r.get(name), (int, float)))

    return {
        "n": len(rows),
        "failed": sum(1 for r in rows if r.get("error")),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "cost_usd": total("cost_usd"),
        "hosts": dict(Counter(str(r.get("host")) for r in rows)),
    }


# --- claim judges ------------------------------------------------------------------------


async def judge_stage(ctx: Ctx, name: str, judge: Any, verify: Callable[..., Any]) -> dict:
    """Judge every cited claim of every answer with one judge; one row per answer.

    Raises:
        StageOrderError: The answer stage of this run has not finished.
        JudgeUnavailable: The judge cannot start; nothing more is sent.
    """
    from omrs.core.answer.judges.base import JudgeUnavailable

    if not (ctx.run_dir / ".done-answer.json").exists():
        raise StageOrderError(f"judge {name} needs the finished answer stage in {ctx.run_dir}")
    order = {q.qid: i for i, q in enumerate(ctx.questions)}
    answers = sorted(
        outputs35.read_rows(ctx.run_dir / "answer.jsonl"), key=lambda r: order.get(r["qid"], 0)
    )
    log = outputs35.RowFile(ctx.run_dir, f"judge-{name}", ctx.key, resume=ctx.resume)
    if log.done:
        say(f"[judge {name}] {ctx.dataset}/{ctx.arm.name}/run{ctx.run}: done earlier, skipped")
        return _judge_summary(log.rows())
    done = log.done_ids("qid")
    for answer in answers:
        if answer["qid"] in done:
            continue
        started = time.perf_counter()
        row: dict[str, Any] = {
            "qid": answer["qid"],
            "judge": name,
            "verdicts": [],
            "verified": None,
            "skipped_reason": None,
            "error": None,
        }
        if answer.get("error") or not answer.get("answer"):
            row["error"] = "no answer to judge"
        else:
            try:
                outcome = await verify(answer["answer"], answer["evidence"], judge)
                row["verdicts"] = [
                    {
                        "index": i,
                        "ordinals": list(v.ordinals),
                        "verdict": v.verdict,
                        "call": v.call.as_dict() if v.call is not None else None,
                    }
                    for i, v in enumerate(outcome.verdicts)
                ]
                row["verified"], row["skipped_reason"] = outcome.verified, outcome.skipped_reason
            except JudgeUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the row (D8), except for the main checker
                if name == arms.MAIN_JUDGE:
                    # Protocol 4.4: a failed GLM-5.3 call stops the run before this answer is
                    # saved, so `--resume` retries it. No checker takes over by itself.
                    raise JudgeUnavailable(
                        f"claim judge {name} call failed, run again with --resume: "
                        f"{_error(ctx, exc)}"
                    ) from exc
                row["error"] = _error(ctx, exc)
        row["seconds"] = round(time.perf_counter() - started, 3)
        log.append(row)
        status = "error" if row["error"] else ("degraded" if row["skipped_reason"] else "ok")
        ctx.trace.write(
            stage=f"judge-{name}",
            dataset=ctx.dataset,
            question_id=answer["qid"],
            status=status,
            error=row["error"] or row["skipped_reason"],
            durations_s={"judge": row["seconds"]},
            answer_model=arms.ANSWER_MODEL,
            judge_model=_judge_model(name, row["verdicts"]),
        )
        say(f"[judge {name}] {answer['qid']}: {len(row['verdicts'])} claims, {row['seconds']}s")
    summary = _judge_summary(log.rows())
    outputs35.write_json(ctx.run_dir / f"judge-{name}-summary.json", summary)
    log.mark_done(summary)
    return summary


def _judge_model(name: str, verdicts: Sequence[Mapping[str, Any]]) -> str:
    calls = [v["call"] for v in verdicts if v.get("call")]
    return str(calls[0]["model"]) if calls else name


def _judge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    verdicts = Counter(v["verdict"] for r in rows for v in r["verdicts"])
    return {
        "answers": len(rows),
        "claims": sum(verdicts.values()),
        "verdicts": dict(verdicts),
        "errors": sum(1 for r in rows if r.get("error")),
        "skipped": sum(1 for r in rows if r.get("skipped_reason")),
        "calls_without_record": sum(1 for r in rows for v in r["verdicts"] if not v.get("call")),
    }


# --- determinism -------------------------------------------------------------------------


def _by_run(folder: Path, runs: Sequence[int], name: str, value: Callable) -> dict | None:
    found = {
        run: {row["qid"]: value(row) for row in outputs35.read_rows(folder / f"run{run}" / name)}
        for run in runs
        if (folder / f"run{run}" / name).exists()
    }
    return found if len(found) >= 2 else None


def determinism_stage(layout: outputs35.Layout, dataset: str, arm: str) -> dict[str, Any]:
    """Compare the runs of one arm: retrieved IDs, answer text and each judge's verdicts.

    Raises:
        ValueError: Fewer than two runs have a search file.
    """
    folder = layout.arm_dir(dataset, arm)
    runs = sorted(
        int(p.name.removeprefix("run"))
        for p in folder.glob("run*")
        if (p / "search.jsonl").exists()
    )
    retrieval = _by_run(folder, runs, "search.jsonl", lambda row: row["ranked_ids"])
    if retrieval is None:
        raise ValueError(f"determinism needs two runs with a search file in {folder}")
    answers = _by_run(
        folder,
        runs,
        "answer.jsonl",
        lambda row: [hashlib.sha256(row["answer"].encode("utf-8")).hexdigest()],
    )
    judge_files = sorted({p.name for p in folder.glob("run*/judge-*.jsonl")})
    verdicts = {}
    for file in judge_files:
        found = _by_run(folder, runs, file, lambda row: [v["verdict"] for v in row["verdicts"]])
        if found is not None:
            verdicts[file.removeprefix("judge-").removesuffix(".jsonl")] = compare_runs(
                found
            ).to_dict()
    report = {
        "runs": runs,
        "retrieval": compare_runs(retrieval).to_dict(),
        "answers": compare_runs(answers).to_dict() if answers else None,
        "verdicts": verdicts,
    }
    outputs35.write_json(folder / "determinism.json", report)
    say(f"[determinism] {dataset}/{arm}: retrieval ok={report['retrieval']['ok']}")
    return report
