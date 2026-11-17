"""Shared parts of the Experiment 35 search, answer and judge stages.

* :func:`qwen3_tokens`: the one place that loads the pinned Qwen3 tokenizer
  (lazily, on first use). Tests put their own counter on ``ctx.tokens``.
* :func:`ranked`: one unassembled search at depth 100 (``top_k`` and
  ``fetch_k`` 100, task 0.7a) and the saved form of its stored chunks.
* :func:`drain`: a worker pool. The first exception stops new sends; the
  calls in flight finish; then the exception is raised.
* :func:`open_checks` and :func:`close_checks`: the fingerprint checks of
  task 5.5 and the rebuild gate (G2) of the shared output folder.

``clock`` is the timer of every saved duration; tests replace it.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import arms
import outputs35
import scoring35
import stages35

#: Ranked list depth of every search (pre-registration section 3).
DEPTH = 100
clock: Callable[[], float] = time.perf_counter


class FingerprintError(RuntimeError):
    """The index or output folder fails a check of task 5.5; exit code 2."""


class RerankFailed(RuntimeError):
    """A reranker-on query came back un-reranked; no row is saved (section 12); exit code 2."""


def require_half_b_open(ctx: Any) -> None:
    """Refuse a main-run replicate stage until half B is open (task 16.17; protocol 0.14 item 54).

    The answer, closed-book, oracle, judge, Ragas and claim-kind stages call
    it before any model call. A pre-freeze or smoke run writes its own folder and skips it.

    Raises:
        scoring35.HalfBLocked: ``scoring35.require_half_b`` refuses the output folder.
    """
    if ctx.args.prefreeze or ctx.args.smoke:
        return
    scoring35.require_half_b(ctx.layout.root)


@dataclass(frozen=True)
class Tokens:
    """A token counter and a truncator on one tokenizer."""

    count: Callable[[str], int]
    truncate: Callable[[str, int], str]


def qwen3_tokens() -> Tokens:
    """Return the pinned Qwen3 tokenizer counter (no special tokens), loaded from the cache."""
    from omrs.integrations.tokenizer import load_tokenizer

    tokenizer = load_tokenizer(arms.TOKENIZER_MODEL, arms.TOKENIZER_REVISION)

    def count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    def truncate(text: str, n: int) -> str:
        found = tokenizer.encode(text, add_special_tokens=False)
        if n >= len(found.ids):
            return text
        return text[: found.offsets[n - 1][1]] if n > 0 else ""

    return Tokens(count, truncate)


def retarget(trace: Any, path: Any) -> Any:
    """Return a trace writer with the run fields of *trace* that writes to *path*."""
    from experiments._lib.trace import TraceWriter

    fields = dict(trace._context)
    return TraceWriter(
        path,
        benchmark_revision=fields["benchmark_revision"],
        run_id=fields["run_id"],
        arm=fields["arm"],
        repetition=fields["repetition"],
        effective_settings=fields["effective_settings"],
        model_identities=fields["model_identities"],
    )


def tokens_of(ctx: Any) -> Tokens:
    """Return ``ctx.tokens``, loading the pinned tokenizer the first time."""
    if ctx.tokens is None:
        ctx.tokens = qwen3_tokens()
    return ctx.tokens


def saved_chunk(row: Mapping[str, Any], tokens: Tokens) -> dict[str, Any]:
    """Return the saved form of one stored chunk: no text, no gold label."""
    return {
        "chunk_id": scoring35.result_id(row),
        "score": row.get("score"),
        "stem": scoring35._stem(row),
        "page_label": row.get("page_label"),
        "tokens": tokens.count(str(row.get("text") or "")),
    }


async def ranked(ctx: Any, text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Search *text* once on the setup's collection; return ``(rows, saved line)``.

    Raises:
        RerankFailed: A reranker-on setup got rows the reranker did not score.
    """
    setup = ctx.factors
    started = clock()
    rows = await asyncio.to_thread(
        ctx.engine.search,
        text,
        collection_name=ctx.collection,
        top_k=DEPTH,
        fetch_k=DEPTH,
        rerank=setup.rerank,
        hybrid=setup.hybrid_on,
        include_diagnostics=True,
        unassembled=True,
    )
    seconds = round(clock() - started, 3)
    if setup.rerank and any(row.get("reranked") is not True for row in rows):
        reason = next((r.get("rerank_reason") for r in rows if r.get("rerank_reason")), None)
        raise RerankFailed(
            f"{ctx.setup}: the reranker did not score the query {text[:80]!r} "
            f"({reason or 'no reason given'}); nothing saved, run again with --resume"
        )
    tokens = tokens_of(ctx)
    line = {
        "chunks": [saved_chunk(row, tokens) for row in rows],
        "seconds": seconds,
        "timings": dict(rows[0].get("timings") or {}) if rows else {},
    }
    return list(rows), line


async def drain(items: Iterable[str], work: Callable[[str], Awaitable[None]], limit: int) -> None:
    """Run *work* on each item with at most *limit* at once, in item order of start.

    Raises:
        BaseException: The first exception of any item, after the calls in
            flight have finished. No item starts after it.
    """
    queue = iter(items)
    stop: list[BaseException] = []

    async def worker() -> None:
        while not stop:
            item = next(queue, None)
            if item is None:
                return
            try:
                await work(item)
            except BaseException as exc:  # noqa: BLE001 - raised after the pool drains
                stop.append(exc)

    await asyncio.gather(*(worker() for _ in range(limit)))
    if stop:
        raise stop[0]


def _fingerprint(ctx: Any) -> dict[str, Any]:
    path = ctx.layout.fingerprint(ctx.dataset, ctx.index)
    if not path.exists():
        raise FingerprintError(f"{path} is missing; seal index {ctx.index} on {ctx.dataset} first")
    return json.loads(path.read_text(encoding="utf-8"))


def _rebuild_gate(ctx: Any) -> None:
    if ctx.layout.index_root is not None:
        return
    path = ctx.layout.root / ctx.dataset / "rebuild.json"
    found = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if found.get("ok") is not True:
        raise FingerprintError(
            f"{ctx.dataset}: no passing rebuild check ({path}); G2 must pass before a stage "
            "writes into the shared output folder (or use --index-from with another --out-dir)"
        )


def open_checks(ctx: Any) -> dict[str, Any]:
    """Check the sealed index and the output folder before the first query.

    Raises:
        FingerprintError: No fingerprint; a hybrid setup resolves another
            sparse backend than the fingerprint; ``native`` with no full-text
            index; a table version other than the sealed one; or a shared
            output folder with no passing ``rebuild.json``.
        outputs35.ResumeMismatchError: The ingest done-marker of the index
            holds another configuration than ``ctx.key["index_config"]``
            (task 3.4, review R2-05); the message names each field.
    """
    _rebuild_gate(ctx)
    sealed = _fingerprint(ctx)
    outputs35.check_index_config(ctx.index_dir, ctx.key["index_config"])
    backend = ctx.settings.retrieval.hybrid_sparse_backend
    if ctx.factors.hybrid_on and sealed.get("sparse_backend") != backend:
        raise FingerprintError(
            f"{ctx.setup} resolves sparse backend {backend!r}; the fingerprint of "
            f"{ctx.index} on {ctx.dataset} holds {sealed.get('sparse_backend')!r}"
        )
    live = stages35._read_index(ctx)
    if ctx.factors.hybrid_on and backend == "native" and live["fts"] is None:
        raise FingerprintError(f"{ctx.collection} has no full-text index for the native backend")
    if live["table_version"] != sealed.get("table_version"):
        raise FingerprintError(
            f"{ctx.collection} is at table version {live['table_version']}; "
            f"the seal recorded {sealed.get('table_version')}"
        )
    return {
        "table_version": live["table_version"],
        "sparse_backend": sealed.get("sparse_backend"),
        "fts": live["fts"],
    }


def close_checks(ctx: Any, opened: Mapping[str, Any]) -> dict[str, Any]:
    """Check that the table did not change during the stage; return the marker's ``checks``.

    Raises:
        FingerprintError: The table version or the full-text counts changed.
    """
    live = stages35._read_index(ctx)
    if live["table_version"] != opened["table_version"] or live["fts"] != opened["fts"]:
        raise FingerprintError(
            f"{ctx.collection} changed during the stage (version {opened['table_version']} "
            f"to {live['table_version']}); no done-marker written"
        )
    return {"fingerprint": dict(opened), "table_version_unchanged": True}
