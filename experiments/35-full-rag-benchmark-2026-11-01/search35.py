"""Experiment 35 search stage (tasks 15.1a, 15.2, 13.7; pre-registration sections 6, 12, 14.2).

``--stage search`` runs one search setup once on every question and saves,
per question, the ranked list of 100 stored chunks (the unassembled search
of task 0.7a, ``top_k`` and ``fetch_k`` 100): chunk ID, score, file stem,
page label and the pinned Qwen3 token count, plus timings. It saves no chunk
text, reads no gold label and computes no metric: ``score35.py`` scores the
saved lists per half, behind the half-B guard.

Files in ``<out>/<dataset>/search/<setup>/run1/``: ``search.jsonl`` (one line
per question, frozen order), ``search-summary.json`` (counts and timings
only) and ``.done-search.json`` (the summary and the fingerprint checks).

Resend rule (section 12): a failed search saves no row and is sent again on
``--resume``; its third error closes the question as missing. A reranker-on
query that comes back un-reranked stops the stage with a setup error (exit
code 2); nothing is saved for it and ``--resume`` sends it again.
"""

from __future__ import annotations

from typing import Any

import outputs35
import stagekit35
import stages35
from experiments._lib.ordered_rows import OrderedRows

say = outputs35.say


async def search_stage(ctx: stages35.Ctx) -> int:
    """Search every open question of the setup once; return 0 when every question has a row.

    Raises:
        stagekit35.FingerprintError: A check of task 5.5 fails.
        stagekit35.RerankFailed: A reranker-on query came back un-reranked.
        stages35.StageIncomplete: Items stay open after their errors.
    """
    with outputs35.RowFile(ctx.run_dir, "search", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[search] {ctx.dataset}/{ctx.setup}: done earlier, skipped")
            return 0
        opened = stagekit35.open_checks(ctx)
        rows = OrderedRows(log, [q.qid for q in ctx.questions], trace=ctx.trace)
        text = {q.qid: q.text for q in ctx.questions}

        async def one(qid: str) -> None:
            rows.dispatch(qid)
            try:
                _, line = await stagekit35.ranked(ctx, text[qid])
            except stagekit35.RerankFailed:
                raise
            except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                error = stages35._error(ctx, exc)
                trace = _trace(ctx, qid, error=error)
                rows.fail(qid, error, trace)
                say(f"[search] {qid}: ERROR {error}")
                return
            rows.submit(qid, {"qid": qid, **line}, _trace(ctx, qid, line=line))

        await stagekit35.drain(rows.todo(), one, 1)
        done = log.rows()
        summary = {
            "questions": len(ctx.questions),
            "rows": sum(1 for r in done if not r.get("missing")),
            "chunks": sum(len(r.get("chunks") or []) for r in done),
            "seconds": round(sum(r.get("seconds") or 0.0 for r in done), 3),
            "resent_calls": rows.resent_calls,
            "closed_missing": rows.closed_missing,
        }
        outputs35.write_json(ctx.run_dir / "search-summary.json", summary)
        checks = stagekit35.close_checks(ctx, opened)
        if not rows.finish({**summary, "checks": checks}):
            raise stages35.StageIncomplete(f"search {ctx.setup}: questions still open")
    say(f"[search] {ctx.dataset}/{ctx.setup}: {summary['rows']} rows")
    return 0


def _trace(
    ctx: stages35.Ctx, qid: str, *, line: dict[str, Any] | None = None, error: str | None = None
) -> dict[str, Any]:
    chunks = (line or {}).get("chunks") or []
    return ctx.trace.row(
        stage="search",
        dataset=ctx.dataset,
        question_id=qid,
        status=stages35._status(error),
        error=error,
        retrieved={"ids": [c["chunk_id"] for c in chunks], "scores": [c["score"] for c in chunks]}
        if line
        else None,
        durations_s={"search": line["seconds"]} if line else None,
    )
