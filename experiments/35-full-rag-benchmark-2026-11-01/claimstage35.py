"""Claim-kinds stage of Experiment 35 (tasks 8.5, 16.29; pre-registration sections 6, 11.1, 12).

``--stage claimkinds`` sorts every claim of one answer run folder, and every
uncited segment (``segments35``), into ``factual``, ``refusal`` or ``mixed``
with A6's fixed-prompt classifier (``claimkinds35``). The classifier sees the
question and the sentence only. Calls go through the hosted gate
(``experiments/_lib/hosted_calls.py``) with at most ``--classify-concurrency``
calls in flight, and through ``OrderedRows`` (the resend rule):

- a reply is final; a reply that is not one of the kinds is saved as ``unreadable``;
- an error that is not a rate limit saves no kind; ``--resume`` sends it again,
  and its third error closes it with ``kind: null`` and ``missing: true``
  (unclassified, treated as factual; section 12);
- a rate limit past the attempts, or out of credit, stops the stage with exit
  code 5; nothing is saved for the calls in flight and no done-marker is written.

Files in ``run<n>/``: ``claim-kinds.jsonl`` (the name every reader uses; rows
``item``, ``claim_key``, ``qid``, ``index``, ``uncited``, ``kind``,
``version``, ``model_returned``, ``provider_returned``), ``.done-claimkinds.json``,
``claimkinds-summary.json`` and the ``claimkinds.*`` key, pending, dispatch and
error files. ``item`` is the claim key, prefixed ``u:`` for an uncited segment.

The runner does the environment check (task 5.6) before the stage, as for
every model stage. Tests put a stub on ``ctx.classifier`` (an async callable
taking chat messages and returning an object with ``text``,
``model_returned`` and ``provider_returned``) and ``ctx.classifier_version``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import claimkinds35
import outputs35
import segments35
import stagekit35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows
from outputs35 import read_rows, say, write_json
from stages35 import StageIncomplete, StageOrderError

__all__ = ["EXIT_RATE_LIMIT", "StageIncomplete", "add_arguments", "claimkinds_stage"]

EXIT_RATE_LIMIT = 5
STAGE = "claimkinds"
ROWS_FILE = "claim-kinds.jsonl"
ROLE = "claim-classifier"
FIELDS = ("model", "provider", "host", "reasoning", "temperature", "seed")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the stage's option: the prompt examples file (``--classify-concurrency`` is in cli35)."""
    parser.add_argument(
        "--classify-examples",
        type=Path,
        help="JSON list of prompt examples (question, claim, kind) for the claimkinds stage",
    )


def _items(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return every claim and uncited segment of the run, in answer order, by item id."""
    items = {c["claim_key"]: {**c, "uncited": False} for c in claimkinds35._todo(run_dir, set())}
    for answer in read_rows(run_dir / "answer.jsonl"):
        qid = str(answer["qid"])
        evidence = len(answer.get("evidence") or [])
        for index, text in enumerate(
            segments35.uncited_segments(answer.get("answer") or "", evidence)
        ):
            key = claimkinds35.claim_key(qid, text)
            items.setdefault(
                f"u:{key}",
                {"claim_key": key, "qid": qid, "index": index, "claim": text, "uncited": True},
            )
    position = {str(a["qid"]): n for n, a in enumerate(read_rows(run_dir / "answer.jsonl"))}
    order = sorted(items, key=lambda i: (position[items[i]["qid"]], items[i]["uncited"]))
    return {i: items[i] for i in order}


class _KindsLog:
    """The stage's ``RowFile`` with rows in ``claim-kinds.jsonl``; a closed row keeps its claim."""

    def __init__(self, log: outputs35.RowFile, items: Mapping[str, Mapping[str, Any]]) -> None:
        self._log = log
        self._items = items
        self.stage = log.stage
        self.path = log.path.with_name(ROWS_FILE)
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                self.path.write_text(text[: text.rfind("\n") + 1], encoding="utf-8")

    def done_ids(self, field: str) -> set[str]:
        return {str(r[field]) for r in read_rows(self.path)}

    def append(self, row: Mapping[str, Any]) -> None:
        if row.get("missing"):
            item = self._items[row["item"]]
            row = {**_row(row["item"], item), "kind": None, **row}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def mark_done(self, payload: Mapping[str, Any]) -> None:
        self._log.mark_done(payload)


def _row(item_id: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "item": item_id,
        "claim_key": item["claim_key"],
        "qid": item["qid"],
        "index": item["index"],
        "uncited": item["uncited"],
    }


def _classifier(ctx: Any) -> tuple[Callable[[list[dict[str, str]]], Awaitable[Any]], str, str]:
    """Return the classifier call, its version and its prompt; tests set ``ctx.classifier``."""
    if getattr(ctx, "classifier", None) is not None:
        return ctx.classifier, ctx.classifier_version, claimkinds35.PROMPT
    import ragas35_judge

    examples = json.loads(Path(ctx.args.classify_examples).read_text(encoding="utf-8"))
    prompt = claimkinds35.build_prompt(examples)
    found = [r for r in ctx.plan["runtime"]["references"] if r.get("role") == ROLE]
    missing = [f for f in FIELDS if f not in (found[0] if found else {})]
    if missing:
        raise ValueError(f"plan.json {ROLE} lacks {', '.join(missing)}")
    settings = {f: found[0][f] for f in FIELDS}
    send, built = ragas35_judge.build_judge(settings)
    ragas35_judge.check_built(settings, built)
    version = claimkinds35.classifier_version(
        prompt, **{k: settings[k] for k in ("model", "host", "reasoning", "temperature", "seed")}
    )

    async def call(messages: list[dict[str, str]]) -> Any:
        return await send("\n\n".join(m["content"] for m in messages))

    return call, version, prompt


async def claimkinds_stage(
    ctx: Any, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
) -> int:
    """Classify every open claim and uncited segment of ``ctx.run_dir``; return 0 or 5.

    Raises:
        StageIncomplete: An item stays open after its errors; ``--resume`` sends it again.
        StageOrderError: The run folder has no finished answer stage (names it).
        scoring35.HalfBLocked: A main run while half B is locked.
    """
    stagekit35.require_half_b_open(ctx)
    if not (ctx.run_dir / ".done-answer.json").exists():
        raise StageOrderError(f"the claimkinds stage needs a finished answer stage in {ctx.run_dir}")
    call, version, prompt = _classifier(ctx)
    questions = {str(q.qid): q.text for q in ctx.questions}
    with outputs35.RowFile(ctx.run_dir, STAGE, ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[claimkinds] {ctx.run_dir}: done earlier, skipped")
            return 0
        items = _items(ctx.run_dir)
        rows = OrderedRows(_KindsLog(log, items), list(items), id_field="item")
        limit = int(ctx.args.classify_concurrency)
        gate = HostedGate(ROLE, limit, attempts=int(ctx.args.rate_limit_attempts), sleep=sleep)
        slots = asyncio.Semaphore(limit)
        stopped: list[str] = []

        async def one(item_id: str) -> None:
            async with slots:
                if stopped:
                    return
                item = items[item_id]
                messages = claimkinds35.messages(prompt, questions[item["qid"]], item["claim"])
                rows.dispatch(item_id)
                try:
                    reply = await gate.call(lambda: call(messages))
                except RateLimitStop as exc:
                    stopped.append(str(exc))
                    return
                except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                    rows.fail(item_id, f"{type(exc).__name__}: {exc}"[:500])
                    return
                rows.submit(
                    item_id,
                    {
                        **_row(item_id, item),
                        "kind": claimkinds35.parse_kind(str(reply.text)),
                        "version": version,
                        "model_returned": getattr(reply, "model_returned", None),
                        "provider_returned": getattr(reply, "provider_returned", None),
                    },
                )

        await asyncio.gather(*(one(i) for i in rows.todo()))
        saved = read_rows(ctx.run_dir / ROWS_FILE)
        kinds = Counter(r["kind"] or "unclassified" for r in saved)
        summary = {
            "items": len(items),
            "rows": len(saved),
            "uncited": sum(1 for i in items.values() if i["uncited"]),
            "kinds": dict(sorted(kinds.items())),
            "version": version,
            "resent_calls": rows.resent_calls,
            "closed_missing": rows.closed_missing,
        }
        write_json(ctx.run_dir / "claimkinds-summary.json", summary)
        if stopped:
            say(f"[claimkinds] stopped: {stopped[0]}")
            return EXIT_RATE_LIMIT
        if not rows.finish(summary):
            raise StageIncomplete(f"claimkinds {ctx.run_dir}: items still open")
    say(f"[claimkinds] {ctx.run_dir}: {len(saved)} kinds")
    return 0
