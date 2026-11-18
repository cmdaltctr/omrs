"""Ragas stage of the Experiment 35 main run (tasks 7.1 to 7.4, 14.5, 15.9; design D6, D33).

``ragas_stage(ctx, plan)`` scores every answer of one run folder with five
Ragas 0.4.3 metrics through the custom adapter of ``prefreeze/ragas_stage.py``
(ruling R-5): faithfulness, answer relevancy, context precision, context recall
and answer correctness. It reads ``run<n>/answer.jsonl`` and writes, in the same
folder:

- ``ragas.jsonl``: one final row per answer, in frozen question order;
- ``ragas.partial.jsonl``: a row that still has an open failed metric (its
  scored metrics and its ``unjudged`` list); the last line per question counts;
- ``ragas.metric-errors.jsonl``: one line per failed metric call;
- ``ragas-summary.json`` at every exit, and ``.done-ragas.json`` when every
  answer has a final row.

Resend rule (pre-registration section 12, ruling R-3). A failed metric is never a
score. ``--resume`` runs only the open metrics of an answer again and never a
scored one. The third error of a metric (first send plus 2 resends, across
resumes) closes it: the final row keeps it in ``unjudged`` with ``closed: true``.
A metric call that returns NaN (or no number) returned content: the score is
saved as ``null`` with ``not_defined``, counted in the summary, never resent and
never counted toward the cap (review R2-14). A returned empty answer is judged
like any other answer; only a missing or error row gets ``not_judged`` (R2-03).
Side files drop a cut last line on read (R2-09).
A rate-limit stop (the hosted gate) returns :data:`EXIT_RATE_LIMIT`. The answer
in flight keeps the metrics it had scored as a partial row, so ``--resume``
scores only the others; the metric that hit the stop is not saved (issue 217).

The judge settings and seed come from ``plan.json`` (H-11). The embeddings use
the plan's 4B file through one router session held for the whole stage (H-17).
Ragas lives in a separate environment and is imported only inside the builders.
"""

from __future__ import annotations

import asyncio
import math
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_PREFREEZE = Path(__file__).resolve().parent / "prefreeze"
if str(_PREFREEZE) not in sys.path:
    sys.path.insert(0, str(_PREFREEZE))

import outputs35  # noqa: E402
import ragas_stage as ragas_stage_lib  # noqa: E402
import stagekit35  # noqa: E402
from experiments._lib.hosted_calls import HostedGate, RateLimitStop  # noqa: E402
from experiments._lib.ordered_rows import (  # noqa: E402
    ERROR_CAP,
    OrderedRows,
    append_line,
    read_lines,
)
from experiments._lib.router_env import model_name  # noqa: E402
from ragas35_judge import (  # noqa: E402
    RagasParts,
    RagasRefused,
    built_judge_values,
    check_built,
    judge_settings,
    main_metrics,
)

STAGE = "ragas"
METRICS = (
    "ragas_faithfulness",
    "ragas_answer_relevancy",
    "ragas_context_precision",
    "ragas_context_recall",
    "ragas_answer_correctness",
)
"""Saved metric names, as ``plan.json`` names them."""
REFERENCE_METRICS = frozenset(
    {"ragas_context_precision", "ragas_context_recall", "ragas_answer_correctness"}
)
EMBED_ROLE = "embedding-baseline-4b"
EXIT_RATE_LIMIT = 5
"""A rate-limit stop: nothing more was sent; ``--resume`` goes on."""
EXIT_OPEN = 6
"""A metric failed and is still open; run the stage again with ``--resume``."""
NO_ANSWER = "no answer text"
NO_REFERENCE = "no reference answer"
__all__ = [
    "EXIT_OPEN",
    "EXIT_RATE_LIMIT",
    "METRICS",
    "RagasParts",
    "RagasRefused",
    "add_arguments",
    "built_judge_values",
    "judge_settings",
    "main_metrics",
    "ragas_stage",
]


def add_arguments(parser: Any) -> None:
    """Add ``--ragas-host`` and ``--ragas-venv`` to *parser*.

    ``--ragas-concurrency`` belongs to the runner (``cli35``, default from
    ``arms.CONCURRENCY_DEFAULTS``).
    """
    parser.add_argument("--ragas-host", default="", help="the one pinned Ragas judge host")
    parser.add_argument("--ragas-venv", type=Path, default=None, help="the Ragas environment")


# --- files -----------------------------------------------------------------------


#: A cut last line (a stop part-way through an append) is dropped (review R2-09).
_read = read_lines
_append = append_line


# --- one answer -----------------------------------------------------------------


def _row(
    header: Mapping[str, Any],
    qid: str,
    metrics: Mapping[str, Any],
    errors: Mapping[str, list[str]],
    calls: list[dict[str, Any]],
    not_judged: str | None = None,
) -> dict[str, Any]:
    unjudged = [
        {
            "metric": m,
            "errors": len(errors[m]),
            "error": errors[m][-1],
            "closed": len(errors[m]) >= ERROR_CAP,
        }
        for m in METRICS
        if m not in metrics and errors.get(m)
    ]
    return {
        **header,
        "qid": qid,
        "not_judged": not_judged,
        "metrics": dict(metrics),
        "unjudged": unjudged,
        "model_returned": sorted({c["model_returned"] for c in calls if c.get("model_returned")}),
        "provider_returned": sorted(
            {c["provider_returned"] for c in calls if c.get("provider_returned")}
        ),
        "calls": calls,
    }


class _JudgeStop(RateLimitStop):
    """A rate-limit stop inside one answer, with the metrics scored before it."""

    def __init__(
        self,
        message: str,
        records: dict[str, Any],
        failed: list[tuple[str, str]],
        calls: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.records, self.failed, self.calls = records, failed, calls


async def _judge(
    sample: Mapping[str, Any],
    prev: Mapping[str, Any] | None,
    errors: Mapping[str, list[str]],
    seam: Any,
    scorers: Mapping[str, Any],
    clock: Callable[[], float],
) -> tuple[dict[str, Any], list[tuple[str, str]], list[dict[str, Any]]]:
    """Run the open metrics of one answer; return its metric records, new errors and calls."""
    records = dict(prev["metrics"]) if prev else {}
    seam.calls = list(prev["calls"]) if prev else []
    failed: list[tuple[str, str]] = []
    for name in METRICS:
        if name in records or len(errors.get(name, [])) >= ERROR_CAP:
            continue
        if name in REFERENCE_METRICS and not sample["reference"]:
            records[name] = {"score": None, "not_judged": NO_REFERENCE, "calls": 0}
            continue
        seam.metric, first, started = name, len(seam.calls), clock()
        try:
            score = await scorers[name](sample)
        except Exception as exc:  # noqa: BLE001 - a failed metric stays open (R-3)
            # The seam saw the gate stop, whatever error Ragas wrapped it in.
            if any(c.get("error") == "RateLimitStop" for c in seam.calls[first:]):
                raise _JudgeStop(
                    f"{name}: rate-limit stop inside Ragas", records, failed, seam.calls[:first]
                ) from exc
            failed.append((name, type(exc).__name__))
            continue
        undefined = score is None or math.isnan(score)
        records[name] = ragas_stage_lib._metric_record(
            None if undefined else score, seam.calls[first:], clock() - started, ""
        )
        if undefined:  # returned content: final, never resent (review R2-14)
            records[name]["not_defined"] = f"score is {'NaN' if score is not None else 'None'}"
    return records, failed, seam.calls


# --- the stage -----------------------------------------------------------------


def _summary(
    ctx: Any, final: Sequence[Mapping], open_rows: Sequence[Mapping], errors: int, resent: int
) -> dict:
    closed: Counter[str] = Counter()
    for row in final:
        closed.update(u["metric"] for u in row.get("unjudged", []) if u["closed"])
    still_open: Counter[str] = Counter()
    for row in open_rows:
        still_open.update(u["metric"] for u in row["unjudged"] if not u["closed"])
    undefined = Counter(
        m for r in final for m, v in r.get("metrics", {}).items() if v.get("not_defined")
    )
    return {
        "setup": ctx.setup,
        "answers": len(ctx.questions),
        "rows": len(final),
        "not_judged": sum(1 for r in final if r.get("not_judged")),
        "errors": errors,
        "unjudged_open": dict(sorted(still_open.items())),
        "unjudged_closed": dict(sorted(closed.items())),
        "not_defined": dict(sorted(undefined.items())),
        "calls": sum(len(r.get("calls", [])) for r in final),
        "resent_calls": resent,
    }


async def ragas_stage(
    ctx: Any,
    plan: Mapping[str, Any],
    *,
    parts: RagasParts | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Score every answer of ``ctx.run_dir`` with the five Ragas metrics.

    Args:
        ctx: The stage context; the build note lists the fields it reads.
        plan: The ``plan.json`` mapping.
        parts: The Ragas pieces; the real ones by default.
        sleep: The rate-limit gate's sleep (tests pass a stub).

    Returns:
        0 when every answer has a final row, :data:`EXIT_RATE_LIMIT` after a
        rate-limit stop, or :data:`EXIT_OPEN` while a failed metric is open.

    Raises:
        RagasRefused: No host, a plan setting missing or different, no finished
            answer stage, or a built judge that differs from the plan.
        ragas_stage.RagasMissingError: Ragas is missing or not version 0.4.3.
        Exception: The runtime check's error, before any paid call.
        scoring35.HalfBLocked: A main run while half B is locked.
    """
    stagekit35.require_half_b_open(ctx)
    parts = parts or RagasParts()
    args = ctx.args
    settings = judge_settings(plan, args.ragas_host)
    version = parts.require(args.ragas_venv)
    if args.dry_run:
        print(
            f"[ragas dry-run] judge {settings['model']} via {settings['provider']}, "
            f"host {settings['host']}, reasoning {settings['reasoning']}, "
            f"temperature {settings['temperature']}, seed {settings['seed']}, "
            f"Ragas {version}; nothing sent",
            flush=True,
        )
        return 0
    run_dir = Path(ctx.run_dir)
    if not (run_dir / ".done-answer.json").exists():
        raise RagasRefused(f"the ragas stage needs the finished answer stage in {run_dir}")
    send, built = parts.judge(settings)
    check_built(settings, built)
    entry = next(m for m in plan["runtime"]["models"] if m["role"] == EMBED_ROLE)
    with outputs35.RowFile(run_dir, STAGE, ctx.key, resume=ctx.resume) as log:
        if log.done:
            print(f"[ragas] {run_dir}: done earlier, skipped", flush=True)
            return 0
        rows = OrderedRows(log, [q.qid for q in ctx.questions])
        todo = rows.todo()
        with ctx.router(entry) as endpoint:
            found = ctx.runtime_check(entry, endpoint)
            embedding = {
                "endpoint": endpoint,
                "file": entry["file"],
                "build": found["build"],
                "sha256": found["sha256"],
            }
            header = {
                "setup": ctx.setup,
                "judge_model": settings["model"],
                "judge_provider": settings["provider"],
                "judge_host": settings["host"],
                "reasoning": settings["reasoning"],
                "temperature": settings["temperature"],
                "seed": settings["seed"],
                "ragas_version": version,
                **{f"embedding_{k}": v for k, v in embedding.items()},
            }
            embeddings = parts.embeddings(endpoint, model_name(entry))
            code, weights = await _run(ctx, rows, todo, header, send, embeddings, parts, sleep)
        return _close(ctx, log, rows, code, settings, version, weights, embedding)


async def _run(
    ctx: Any,
    rows: OrderedRows,
    todo: list[str],
    header: Mapping[str, Any],
    send: Callable[[str], Awaitable[Any]],
    embeddings: Any,
    parts: RagasParts,
    sleep: Callable[[float], Awaitable[None]],
) -> tuple[int, dict]:
    """Judge the *todo* answers with one seam and metric set per worker."""
    run_dir = Path(ctx.run_dir)
    answers = {r["qid"]: r for r in _read(run_dir / "answer.jsonl")}
    questions = {q.qid: q for q in ctx.questions}
    partial = {r["qid"]: r for r in _read(run_dir / f"{STAGE}.partial.jsonl")}
    errors: dict[str, dict[str, list[str]]] = {}
    for line in _read(run_dir / f"{STAGE}.metric-errors.jsonl"):
        errors.setdefault(line["id"], {}).setdefault(line["metric"], []).append(line["error"])
    gate = HostedGate(
        STAGE, ctx.args.ragas_concurrency, attempts=ctx.args.rate_limit_attempts, sleep=sleep
    )

    async def gated(prompt: str) -> Any:
        return await gate.call(lambda: send(prompt))

    workers = []
    for _ in range(max(1, min(ctx.args.ragas_concurrency, len(todo)))):
        seam = ragas_stage_lib.RecordingSeam(gated, clock=parts.clock)
        workers.append((seam, *parts.metrics(seam, embeddings)))
    queue: asyncio.Queue[str] = asyncio.Queue()
    for qid in todo:
        queue.put_nowait(qid)
    stop: list[str] = []

    async def work(seam: Any, scorers: Mapping[str, Any]) -> None:
        while not stop and not queue.empty():
            qid = queue.get_nowait()
            answer = answers.get(qid) or {}
            text = None if answer.get("error") or answer.get("missing") else answer.get("answer")
            if text is None:  # no returned answer; an empty one is judged (review R2-03)
                rows.submit(qid, _row(header, qid, {}, {}, [], NO_ANSWER))
                continue
            sample = {
                "qid": qid,
                "question": questions[qid].text,
                "answer": text,
                "contexts": [e["text"] for e in answer.get("evidence") or []],
                "reference": questions[qid].reference,
            }
            mine = errors.setdefault(qid, {})
            rows.dispatch(qid)
            stopped = False
            try:
                records, failed, calls = await _judge(
                    sample, partial.get(qid), mine, seam, scorers, parts.clock
                )
            except _JudgeStop as exc:
                stop.append(str(exc))
                stopped = True
                records, failed, calls = exc.records, exc.failed, exc.calls
            for name, error in failed:
                _append(
                    run_dir / f"{STAGE}.metric-errors.jsonl",
                    {"id": qid, "metric": name, "error": error},
                )
                mine.setdefault(name, []).append(error)
            row = _row(header, qid, records, mine, calls)
            if stopped:  # keep what was scored; the metric that hit the stop is not saved
                if failed or len(records) > len((partial.get(qid) or {}).get("metrics", {})):
                    partial[qid] = row
                    _append(run_dir / f"{STAGE}.partial.jsonl", row)
                return
            if any(not u["closed"] for u in row["unjudged"]):
                partial[qid] = row
                _append(run_dir / f"{STAGE}.partial.jsonl", row)
            else:
                rows.submit(qid, row)

    await asyncio.gather(*(work(seam, scorers) for seam, scorers, _ in workers))
    if stop:
        print(f"[ragas] stopped: {stop[0]}", flush=True)
        return EXIT_RATE_LIMIT, workers[0][2]
    return 0, workers[0][2]


def _close(
    ctx: Any,
    log: Any,
    rows: OrderedRows,
    code: int,
    settings: Mapping[str, Any],
    version: str,
    weights: Mapping[str, Any],
    embedding: Mapping[str, Any],
) -> int:
    """Write the summary; write the done-marker when every answer has a final row."""
    run_dir = Path(ctx.run_dir)
    final = log.rows()
    done = {r["qid"] for r in final}
    latest = {r["qid"]: r for r in _read(run_dir / f"{STAGE}.partial.jsonl")}
    open_rows = [r for q, r in latest.items() if q not in done and r["unjudged"]]
    errors = len(_read(run_dir / f"{STAGE}.metric-errors.jsonl"))
    summary = _summary(ctx, final, open_rows, errors, rows.resent_calls)
    outputs35.write_json(run_dir / f"{STAGE}-summary.json", summary)
    if code:
        return code
    marker = {
        **summary,
        "judge": dict(settings),
        "ragas_version": version,
        "weights": dict(weights),
        "embedding": dict(embedding),
    }
    if rows.finish(marker):
        return 0
    print(
        f"[ragas] {run_dir}: {sum(summary['unjudged_open'].values())} metric(s) failed and stay "
        "open; run the same command with --resume",
        flush=True,
    )
    return EXIT_OPEN
