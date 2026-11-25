"""Experiment 35 closed-book stage (tasks 15.4 stage part, 15.15; pre-registration section 13).

``--stage closedbook --setup <answer setup>`` asks the answer model every
question once (run 1) with no evidence and no search call, with two prompts:

* ``own``: :data:`OWN_PROMPT` asks for an answer from the model's own
  knowledge (the floor), into ``<out>/<dataset>/closedbook-own/<setup>/run1``;
* ``rag``: the main OMRS answer prompt with an empty evidence block, into
  ``<out>/<dataset>/closedbook-rag/<setup>/run1``. A recorded drop step 3
  (``drops.json``, pre-registration section 17) skips this prompt.

Each prompt is one completion call through the hosted gate, with the frozen
answer settings, so every closed-book answer is one round. Rows follow the
answer-row shape of ``answers35.py`` (``evidence`` is empty) plus ``prompt``.
The resend rule of section 12 applies as in the answer stage. ``ragas`` and
the number match read the folders with ``--answers closedbook-own`` or
``closedbook-rag``.
"""

from __future__ import annotations

from typing import Any

import answers35
import budget35
import outputs35
import stagekit35
import stages35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows

say = outputs35.say
#: The own-knowledge prompt (floor). Its SHA-256 is pinned in ``plan.json`` ``pins.prompts``.
OWN_PROMPT = (
    "Answer the question from your own knowledge. Be concise and give the answer "
    "directly.\nQuestion: {query}\nAnswer: "
)
#: Drop step that removes the RAG-prompt run (``budget35.DROP_STEPS``).
RAG_PROMPT_DROP = 3


def prompt_text(kind: str, query: str) -> str:
    """Return the closed-book prompt *kind* (``own`` or ``rag``) for *query*."""
    if kind == "own":
        return OWN_PROMPT.format(query=query)
    from omrs.core.answer.prompt import GROUND_TEXT_QA_TEMPLATE

    return GROUND_TEXT_QA_TEMPLATE.format(context_str="", query_str=query)


async def ask(engine: Any, collection: str, prompt: str) -> dict[str, Any]:
    """Send *prompt* once to OMRS's answer model; return a result with usage and sampling."""
    from omrs.engine_answer import CompletionLedger, prepare_models

    ledger = CompletionLedger()
    complete, *_ = await prepare_models(engine, engine.resolve_settings(collection), None, ledger)
    text = await complete(prompt)
    return ledger.attach({"status": "answered", "answer": text})


async def _one_prompt(ctx: stages35.Ctx, kind: str) -> None:
    folder = ctx.layout.run_dir(ctx.dataset, f"closedbook-{kind}", ctx.setup, ctx.run)
    with outputs35.RowFile(folder, "answer", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[closedbook-{kind}] {ctx.dataset}/{ctx.setup}: done earlier, skipped")
            return
        trace = stagekit35.retarget(ctx.trace, folder / "traces.jsonl")
        kept = OrderedRows(log, [q.qid for q in ctx.questions], trace=trace)
        gate = HostedGate(
            "answer", ctx.args.answer_concurrency, attempts=ctx.args.rate_limit_attempts
        )
        by_id = {q.qid: q for q in ctx.questions}

        async def one(qid: str) -> None:
            prompt = prompt_text(kind, by_id[qid].text)
            kept.dispatch(qid)
            started = stagekit35.clock()
            try:
                result = await gate.call(
                    lambda: answers35.with_finish_reasons(
                        lambda: ask(ctx.engine, ctx.collection, prompt)
                    )
                )
            except RateLimitStop:
                raise
            except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                error = stages35._error(ctx, exc)
                kept.fail(qid, error, answers35._trace(ctx, qid, None, error, trace))
                return
            seconds = round(stagekit35.clock() - started, 3)
            row = answers35.answer_row(ctx, by_id[qid], result, seconds)
            row.update(setup=ctx.setup, prompt=kind, completion_calls=1)
            kept.submit(qid, row, answers35._trace(ctx, qid, row, None, trace))

        await stagekit35.drain(kept.todo(), one, ctx.args.answer_concurrency)
        summary = answers35.summary_of(ctx, log.rows(), kept)
        outputs35.write_json(folder / "answer-summary.json", summary)
        if not kept.finish({**summary, "prompt": kind}):
            raise stages35.StageIncomplete(f"closed-book {kind}: questions still open")


async def closedbook_stage(ctx: stages35.Ctx) -> int:
    """Run the own-knowledge prompt, then the RAG prompt unless dropped; return 0.

    Raises:
        stages35.StageOrderError: A run other than run 1, or no ``selection.json``
            naming this answer setup (main run, review R2-04).
        scoring35.HalfBLocked: A main run while half B is locked.
        RateLimitStop: Rate-limited past the attempt limit, or out of credit.
        stages35.StageIncomplete: Items stay open after their errors.
    """
    if ctx.run != 1:
        raise stages35.StageOrderError("the closed-book stage runs once, as run 1")
    answers35.require_selection(ctx)
    await _one_prompt(ctx, "own")
    if RAG_PROMPT_DROP in budget35.read_drops(ctx.layout.root):
        say("[closedbook-rag] dropped (drop step 3 in drops.json); one closed-book run")
        return 0
    await _one_prompt(ctx, "rag")
    return 0
