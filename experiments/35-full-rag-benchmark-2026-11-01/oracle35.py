"""Experiment 35 oracle contexts and the oracle stage (tasks 15.12, 15.13; design D36; section 13).

The oracle run gives the answer model the gold units as evidence, with no
search call: the Legal gold passage, the FinanceBench gold page texts (read
from the PDF pages with the pinned OMRS reader), the BioASQ gold passages
and the FreshStack gold documents in qrels order. Unit texts come from the
prepared passage files (``--passages-dir``), the same text the index holds.
Every context is capped at 20,480 Qwen3 tokens with the rule of task 15.14
(``scoring35.evidence_by_tokens``); the truncation is recorded per question.

``--stage oracle --setup <answer setup>`` runs once (run 1) into
``<out>/<dataset>/oracle/<setup>/run1/answer.jsonl`` with the answer-row shape
of ``answers35.py`` plus an ``oracle`` record. The judge and Ragas stages read
it with ``--answers oracle``. Descriptive only: no distractors, so it is an
upper bound, not a fair comparison with retrieval.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import answers35
import datasets35
import outputs35
import scoring35
import stagekit35
import stages35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows

say = outputs35.say
#: Returns the text of one FinanceBench page: ``(document, page label) -> text``.
PageReader = Callable[[str, str], str | None]


def _read(path: Path, unit: str, dataset: str) -> str:
    if not path.exists():
        raise datasets35.DatasetError(f"{dataset}: gold unit {unit} has no passage file {path}")
    return path.read_text(encoding="utf-8")


def gold_rows(
    dataset: str, question: Any, *, passages: Path | None, pages: PageReader | None
) -> list[dict[str, Any]]:
    """Return one evidence row per gold unit of *question*, in gold order.

    Raises:
        datasets35.DatasetError: A gold unit has no text; the message names it.
    """
    rows = []
    stems: dict[str, str] = {}
    if dataset == "freshstack":
        folder = Path(str(passages)) / dataset
        stems = {v: k for k, v in datasets35.freshstack_unit_map(folder).items()}
    for unit in question.relevant:
        if dataset == "financebench":
            doc, _, label = unit.rpartition("#p")
            text = pages(doc, label) if pages is not None else None
            if not text:
                raise datasets35.DatasetError(f"financebench: gold page {unit} has no text")
        elif dataset == "freshstack":
            if unit not in stems:
                raise datasets35.DatasetError(f"freshstack: gold document {unit} is not prepared")
            text = _read(Path(str(passages)) / dataset / f"{stems[unit]}.md", unit, dataset)
        else:
            text = _read(Path(str(passages)) / dataset / f"{unit}.md", unit, dataset)
        rows.append({"chunk_id": unit, "text": text, "source": unit})
    return rows


def oracle_context(rows: Sequence[Mapping[str, Any]], tokens: Any) -> tuple[list[dict], dict]:
    """Cap the gold rows at 20,480 tokens; return ``(evidence rows, oracle record)``."""
    cut = scoring35.evidence_by_tokens(list(rows), tokens.count, tokens.truncate)
    whole = sum(tokens.count(str(r["text"])) for r in rows)
    kept = [{**dict(r), "text": item.text} for r, item in zip(rows, cut.items, strict=False)]
    full = {i.chunk_id for i in cut.items if not i.truncated}
    record = {
        "units": [str(r["chunk_id"]) for r in rows],
        "tokens": cut.cut_total,
        "truncated": [str(r["chunk_id"]) for r in rows if str(r["chunk_id"]) not in full],
        "tokens_dropped": whole - cut.cut_total,
    }
    return kept, record


def pdf_pages(settings: Any, root: Path) -> PageReader:
    """Return a FinanceBench page reader on the pinned OMRS PDF reader (one read per PDF)."""
    from omrs.integrations.pdf.factory import build_pdf_reader

    reader = build_pdf_reader(settings.pdf_reader, settings)
    cache: dict[str, dict[str, str]] = {}

    def page(doc: str, label: str) -> str | None:
        if doc not in cache:
            path = root / "benchmarks" / "financebench" / "pdfs" / f"{doc}.pdf"
            found: dict[str, str] = {}
            for item in reader.load_data(path):
                key = str(item.metadata.get("page_label"))
                found[key] = (found.get(key, "") + "\n\n" + item.text).strip()
            cache[doc] = found
        return cache[doc].get(label)

    return page


async def oracle_stage(ctx: stages35.Ctx, pages: PageReader | None = None) -> int:
    """Answer every question once from its gold units; return 0 when every question has a row.

    Raises:
        stages35.StageOrderError: A run other than run 1, or no ``selection.json``
            naming this answer setup (main run, review R2-04).
        scoring35.HalfBLocked: A main run while half B is locked.
        datasets35.DatasetError: A gold unit has no text (before any call).
        RateLimitStop: Rate-limited past the attempt limit, or out of credit.
        stages35.StageIncomplete: Items stay open after their errors.
    """
    if ctx.run != 1:
        raise stages35.StageOrderError("the oracle stage runs once, as run 1")
    answers35.require_selection(ctx)
    passages = getattr(ctx.args, "passages_dir", None)
    if ctx.dataset == "financebench" and pages is None:
        pages = pdf_pages(ctx.settings, datasets35.data_root())
    tokens = stagekit35.tokens_of(ctx)
    contexts = {
        q.qid: oracle_context(gold_rows(ctx.dataset, q, passages=passages, pages=pages), tokens)
        for q in ctx.questions
    }
    with outputs35.RowFile(ctx.run_dir, "answer", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[oracle] {ctx.dataset}/{ctx.setup}: done earlier, skipped")
            return 0
        kept = OrderedRows(log, [q.qid for q in ctx.questions], trace=ctx.trace)
        gate = HostedGate(
            "answer", ctx.args.answer_concurrency, attempts=ctx.args.rate_limit_attempts
        )
        by_id = {q.qid: q for q in ctx.questions}

        async def one(qid: str) -> None:
            rows, record = contexts[qid]
            kept.dispatch(qid)
            error = None
            started = stagekit35.clock()
            try:
                result = await gate.call(
                    lambda: answers35.with_finish_reasons(
                        lambda: ctx.engine.answer(
                            by_id[qid].text,
                            collection_name=ctx.collection,
                            rows=rows,
                            include_diagnostics=True,
                        )
                    )
                )
                if result.get("answer") is None:
                    error = ctx.redact(str(result.get("error") or "no answer text"))[:500]
            except RateLimitStop:
                raise
            except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                error = stages35._error(ctx, exc)
            if error is not None:
                kept.fail(qid, error, answers35._trace(ctx, qid, None, error))
                return
            seconds = round(stagekit35.clock() - started, 3)
            row = answers35.answer_row(ctx, by_id[qid], result, seconds)
            row.update(oracle=record, **answers35.measure(ctx, rows))
            kept.submit(qid, row, answers35._trace(ctx, qid, row, None))

        await stagekit35.drain(kept.todo(), one, ctx.args.answer_concurrency)
        summary = answers35.summary_of(ctx, log.rows(), kept)
        outputs35.write_json(ctx.run_dir / "answer-summary.json", summary)
        if not kept.finish(summary):
            raise stages35.StageIncomplete(f"oracle {ctx.setup}: questions still open")
    return 0
