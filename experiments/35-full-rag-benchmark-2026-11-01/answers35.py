"""Experiment 35 answer stage (tasks 4.2, 4.3, 14.2, 14.3, 15.2, 15.3, 15.14; section 12).

Order of work per question (fixed by the pre-registration, A5 R-1):

1. Search once with the unassembled option (task 0.7a) at ``top_k`` and
   ``fetch_k`` 100; the full ranked list of 100 stored chunks goes to
   ``retrieval.jsonl`` (the same line shape as ``search.jsonl``, for G1).
2. Take the head: 10 stored chunks, or for a ``-t20k`` setup the cut at
   20,480 Qwen3 tokens of stored chunks (``scoring35.evidence_by_tokens``).
3. Run OMRS ``assemble`` on the kept whole chunks only, with no neighbour
   expansion and the setup's own ``chunking.chunk_overlap``. A truncated
   crossing chunk is appended as its own evidence item, never merged.
4. Call ``Engine.answer`` with ``rows=`` (the ``documents`` profile), through
   the hosted gate (``--answer-concurrency``, ``--rate-limit-attempts``).

Resume and resend rule (section 12): rows reach ``answer.jsonl`` and
``retrieval.jsonl`` in frozen order (``OrderedRows``). Any returned answer
text is final, a refusal or an empty answer included. A failed search, an
exception or an error result with no answer text saves no row; ``--resume``
sends it again, and its third error closes the question as missing. A
rate limit past the attempt limit, or out of credit, stops the stage (exit
code 5) with the finished rows kept and no done-marker. The resend never
reads answer content.

The stage refuses to start without ``<out>/selection.json`` naming this
setup among the 15 answer setups (task 14.3), and while half B is locked
(task 16.17), except in a pre-freeze or smoke run.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import arms
import outputs35
import scoring35
import stagekit35
import stages35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows

from omrs.core.retrieval.assembly import assemble

say = outputs35.say
#: Stored chunks of a crossed setup's evidence.
HEAD = 10


def require_selection(ctx: stages35.Ctx) -> None:
    """Refuse an answer stage whose setup is not an answer setup of ``selection.json``.

    Then refuse while half B is locked (``stagekit35.require_half_b_open``).

    Raises:
        StageOrderError: ``selection.json`` is missing, or this setup is not
            one of the 15 answer setups at the selected sizes.
        scoring35.HalfBLocked: No OSF time-stamp of this selection's hash.
    """
    if ctx.args.prefreeze or ctx.args.smoke:
        return
    path = ctx.layout.root / "selection.json"
    if not path.exists():
        raise stages35.StageOrderError(
            f"{path} is missing; score half A and run the selection rule before answers"
        )
    chosen = json.loads(path.read_text(encoding="utf-8"))
    names = [s.name for s in arms.answer_setups(chosen["embedder"], chosen["reranker"])]
    if ctx.setup not in names:
        raise stages35.StageOrderError(
            f"{ctx.setup} is not an answer setup of {path} ({', '.join(names)})"
        )
    stagekit35.require_half_b_open(ctx)


def evidence_rows(ctx: stages35.Ctx, rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict], int]:
    """Return the evidence rows sent to ``answer`` and the pre-assembly token total.

    The head is cut on stored chunks before any assembly; assembly runs on the
    kept whole chunks; a truncated crossing chunk is appended as its own item.
    """
    from omrs.core.retrieval.pipeline import _strip_internal_result_fields

    tokens = stagekit35.tokens_of(ctx)
    whole: list[dict[str, Any]] = []
    extra: list[dict[str, Any]] = []
    if ctx.factors.t20k:
        cut = scoring35.evidence_by_tokens(list(rows), tokens.count, tokens.truncate)
        for row, item in zip(rows, cut.items, strict=False):
            if item.truncated:
                extra.append({**row, "text": item.text, "truncated": True})
            else:
                whole.append(dict(row))
        total = cut.cut_total
    else:
        whole = [dict(r) for r in rows[:HEAD]]
        total = sum(tokens.count(str(r.get("text") or "")) for r in whole)
    merged = assemble(
        whole,
        chunk_overlap=ctx.settings.chunking.chunk_overlap,
        expand_window=0,
        store=ctx.engine.store,
        collection=ctx.collection,
    )
    return [_strip_internal_result_fields(r) for r in merged] + extra, total


def measure(ctx: stages35.Ctx, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Return evidence characters, truncated passages and characters dropped (task 14.2).

    Computed with OMRS's own ``_fit_and_measure`` on the same rows and the
    setup's answer settings.
    """
    from omrs.core.answer import synthesis
    from omrs.core.answer.evidence import _labelled_nodes
    from omrs.core.answer.stages import prepare_evidence

    block = ctx.settings.answer
    nodes = _labelled_nodes(prepare_evidence(list(rows)))
    fitted, total = synthesis._fit_and_measure(
        nodes, block.context_window, block.max_output_tokens, block.max_rounds
    )
    marker = synthesis._EVIDENCE_TRUNCATED_MARKER
    shown = [n.get_content().replace(marker, "") for n in fitted]
    chars = sum(len(n.get_content() or "") + 1 for n in nodes)
    cut = sum(1 for a, b in zip(nodes, shown, strict=False) if len(b) < len(a.get_content()))
    markers = sum(n.get_content().count(marker) for n in fitted) * len(marker)
    return {
        "evidence_chars": chars,
        "truncated_passages": len(nodes) - len(fitted) + cut,
        "chars_dropped": chars - (total - markers),
    }


class _SplitLog:
    """The answer row file; a row's ``retrieval`` part goes to ``retrieval.jsonl`` first."""

    def __init__(self, log: outputs35.RowFile) -> None:
        self._log = log
        self.path, self.stage = log.path, log.stage
        self._extra = Path(log.path).parent / "retrieval.jsonl"
        done, seen, keep = log.done_ids("qid"), set(), []
        for line in outputs35.read_rows(self._extra):
            if line["qid"] in done and line["qid"] not in seen:
                seen.add(line["qid"])
                keep.append(line)
        tmp = self._extra.with_name(self._extra.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), "utf-8")
        tmp.replace(self._extra)

    def done_ids(self, field: str) -> set[str]:
        return self._log.done_ids(field)

    def mark_done(self, payload: Mapping[str, Any]) -> None:
        self._log.mark_done(payload)

    def append(self, row: Mapping[str, Any]) -> None:
        body = dict(row)
        extra = body.pop("retrieval", None)
        if extra is not None:
            with self._extra.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(extra, ensure_ascii=False) + "\n")
        self._log.append(body)


def answer_row(
    ctx: stages35.Ctx,
    question: Any,
    result: Mapping[str, Any],
    seconds: float,
    cut: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return the saved answer row of one returned result (no retrieval part).

    *cut* names the truncated crossing chunk of a ``-t20k`` cut.
    """
    usage = result.get("usage") or {}
    chat = (result.get("sampling") or {}).get("chat") or {}
    evidence = [
        {
            **{k: e.get(k) for k in ("ordinal", "chunk_id", "chunk_ids", "source", "text")},
            "truncated": e.get("chunk_id") in cut,
        }
        for e in result.get("evidence") or []
    ]
    return {
        "qid": question.qid,
        "dataset": ctx.dataset,
        "setup": ctx.setup,
        "run": ctx.run,
        "doc_id": next(iter(question.gold_pages), None) if ctx.dataset == "financebench" else None,
        "status": result.get("status"),
        "answer": result.get("answer"),
        "citations": list(result.get("citations") or []),
        "evidence": evidence,
        "completion_calls": (result.get("diagnostics") or {}).get("completion_calls"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "cost_usd": usage.get("cost_usd"),
        "host": chat.get("host"),
        "host_in_list": chat.get("host_in_list"),
        # Task 15.9: OMRS names the reply's serving host but not the model the reply
        # names, so the join counts this row's model as ``unknown``.
        "model_returned": None,
        "provider_returned": chat.get("host"),
        "temperature": chat.get("temperature"),
        "seed": chat.get("seed"),
        "seconds": seconds,
    }


def _trace(
    ctx: stages35.Ctx,
    qid: str,
    row: Mapping[str, Any] | None,
    error: str | None,
    trace: Any = None,
) -> dict:
    tokens = {
        k: row[k] for k in ("input_tokens", "output_tokens") if isinstance((row or {}).get(k), int)
    }
    return (trace or ctx.trace).row(
        stage="answer",
        dataset=ctx.dataset,
        question_id=qid,
        status=stages35._status(error),
        error=error,
        retrieved={"ids": [e["chunk_id"] for e in row["evidence"]]} if row else None,
        durations_s={"answer": row["seconds"]} if row else None,
        token_counts=tokens or None,
        answer_model=arms.ANSWER_MODEL,
    )


def summary_of(ctx: stages35.Ctx, rows: Sequence[Mapping[str, Any]], kept: OrderedRows) -> dict:
    """Return the stage summary: counts, tokens, cost and hosts."""

    def total(name: str) -> float:
        return sum(r[name] for r in rows if isinstance(r.get(name), (int, float)))

    return {
        "questions": len(ctx.questions),
        "rows": len(rows),
        "answered": sum(1 for r in rows if not r.get("missing")),
        "missing": sum(1 for r in rows if r.get("missing")),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "cost_usd": total("cost_usd"),
        "hosts": dict(
            sorted(Counter(str(r.get("host")) for r in rows if not r.get("missing")).items())
        ),
        "resent_calls": kept.resent_calls,
        "closed_missing": kept.closed_missing,
    }


async def answer_stage(ctx: stages35.Ctx) -> int:
    """Answer every open question of the setup once; return 0 when every question has a row.

    Raises:
        stages35.StageOrderError: No ``selection.json`` for this setup.
        stagekit35.FingerprintError: A check of task 5.5 fails.
        stagekit35.RerankFailed: A reranker-on query came back un-reranked.
        RateLimitStop: Rate-limited past the attempt limit, or out of credit.
        stages35.StageIncomplete: Items stay open after their errors.
    """
    require_selection(ctx)
    with outputs35.RowFile(ctx.run_dir, "answer", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[answer] {ctx.dataset}/{ctx.setup}/run{ctx.run}: done earlier, skipped")
            return 0
        opened = stagekit35.open_checks(ctx)
        kept = OrderedRows(_SplitLog(log), [q.qid for q in ctx.questions], trace=ctx.trace)
        gate = HostedGate(
            "answer", ctx.args.answer_concurrency, attempts=ctx.args.rate_limit_attempts
        )
        by_id = {q.qid: q for q in ctx.questions}

        async def one(qid: str) -> None:
            question = by_id[qid]
            kept.dispatch(qid)
            error = None
            try:
                found, line = await stagekit35.ranked(ctx, question.text)
                rows, cut_tokens = evidence_rows(ctx, found)
                started = stagekit35.clock()
                result = await gate.call(
                    lambda: ctx.engine.answer(
                        question.text,
                        collection_name=ctx.collection,
                        rows=rows,
                        include_diagnostics=True,
                    )
                )
                seconds = round(stagekit35.clock() - started, 3)
                if result.get("answer") is None:
                    error = ctx.redact(str(result.get("error") or "no answer text"))[:500]
            except (stagekit35.RerankFailed, RateLimitStop):
                raise
            except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                error = stages35._error(ctx, exc)
            if error is not None:
                kept.fail(qid, error, _trace(ctx, qid, None, error))
                say(f"[answer] {qid}: ERROR {error}")
                return
            cut = frozenset(str(r["chunk_id"]) for r in rows if r.get("truncated"))
            row = answer_row(ctx, question, result, seconds, cut)
            row.update(
                cut_tokens=cut_tokens,
                evidence_tokens=sum(
                    stagekit35.tokens_of(ctx).count(str(r.get("text") or "")) for r in rows
                ),
                **measure(ctx, rows),
            )
            kept.submit(
                qid, {**row, "retrieval": {"qid": qid, **line}}, _trace(ctx, qid, row, None)
            )

        await stagekit35.drain(kept.todo(), one, ctx.args.answer_concurrency)
        summary = summary_of(ctx, log.rows(), kept)
        outputs35.write_json(ctx.run_dir / "answer-summary.json", summary)
        checks = stagekit35.close_checks(ctx, opened)
        if not kept.finish({**summary, "checks": checks}):
            raise stages35.StageIncomplete(f"answer {ctx.setup}: questions still open")
    say(f"[answer] {ctx.dataset}/{ctx.setup}/run{ctx.run}: {summary['answered']} answered")
    return 0
