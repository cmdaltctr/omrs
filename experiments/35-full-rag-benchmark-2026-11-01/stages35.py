"""Experiment 35 stage context and the index stages: ingest and seal (design D8, D11, D19, D32).

Every stage is one coroutine ``async def stage(ctx: Ctx) -> int`` that returns
an exit code. ``run_arms.py`` builds the context (settings, router, run guard,
engine) and calls the function its ``STAGE_TABLE`` names. Tests pass a stub
engine in the context.

* ``ingest`` writes one index (one embedder and chunk size) of one dataset into
  the index's own store, one file at a time. A file that fails gets a row and
  no done-marker is written; ``--resume`` sends only the failed files again
  (OMRS replaces one source atomically). An OMRS warning is kept in the row's
  ``warnings`` field and is not a failure (task 5.4b).
* ``seal`` checks the finished ingest and writes the index fingerprint (task
  5.4). It opens the store read-only: it creates and refreshes no full-text
  index, and the table version does not change.

``record_machine`` appends the stage's machine line and compares its
environment record with the build record that ``seal`` writes (task 5.6).
"""

from __future__ import annotations

import faulthandler
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import arms
import outputs35
from experiments._lib.trace import TraceWriter

say = outputs35.say
#: The environment fields every stage must have and match (design D19).
ENV_FIELDS = ("gpu", "image", "llama_cpp_build", "gguf_sha256")


#: A file whose ingest gives no result in this time is stuck. The 2026-11-24 t-fb run hung
#: for 17 min at 0 CPU in the PDF read; the longest pre-freeze file took 42 s.
FILE_WATCHDOG_SECONDS = 600.0
#: The exit code of a stuck file: items still open, run again with ``--resume``.
EXIT_STUCK = 6
#: Delete old table versions after this many ingested files (pre-freeze amendment
#: 2026-11-24, protocol section 7). Each one-file write adds a version, each of the
#: about 13 table opens per file lists them all (0.2 ms at 1 version, 2.4 ms at
#: 6,000 on a Mac), and 64 matches the OMRS fragment compaction threshold.
VERSION_CLEANUP_EVERY = 64
#: The exit that ends a stuck process. A native call cannot be cancelled, and its worker
#: thread would block a normal exit (the thread pool joins its threads at exit).
_hard_exit = os._exit


def _stuck(name: str, seconds: float) -> None:
    """Name the stuck file, print every thread's stack and end the process."""
    say(
        f"[ingest] {name}: no result after {seconds:.0f} s; the stage stops "
        f"(exit {EXIT_STUCK}). Every thread's stack follows. Run again with --resume."
    )
    sys.stdout.flush()
    faulthandler.dump_traceback(all_threads=True)
    sys.stderr.flush()
    _hard_exit(EXIT_STUCK)


class StageOrderError(RuntimeError):
    """A stage needs a stage that has not finished."""


class StageIncomplete(RuntimeError):
    """The stage stopped with open items and wrote no done-marker; ``--resume`` continues it."""


class SealRefused(RuntimeError):
    """The index cannot be sealed. The message names the index, the dataset and the reason."""


class EnvironmentMismatch(RuntimeError):
    """The stage's machine differs from the build record, or a field is missing."""


def _same(text: str) -> str:
    return text


@dataclass
class Ctx:
    """Everything one stage of one dataset and setup needs.

    Attributes:
        dataset: The dataset name.
        setup: The setup name (search and answer stages) or the index name
            (``ingest``, ``seal``).
        kind: ``index``, ``search`` or ``answer`` (``arms.stage_kind``).
        run: The repetition (1, 2 or 3; index stages use 1).
        questions: The selected questions, in frozen order.
        layout: The output layout.
        key: The stage key (``outputs35.run_key`` with configuration fields).
        resume: Continue a started stage.
        trace: The D8 trace writer of the stage folder.
        engine: The OMRS ``Engine`` (a stub in tests).
        settings: The resolved OMRS settings.
        plan: The parsed ``plan.json``.
        args: The parsed command line (``cli35.parse_args``).
        files: The corpus files of an ingest; empty for other stages.
        environment: The stage's environment record (:func:`environment_record`).
        redact: Removes secrets from error text.
        tokens: The Qwen3 token counter (``count``, ``truncate``); ``None``
            loads the pinned tokenizer on first use (``search35.tokens_for``).
        judge: Builds the claim judge of one name (judge stage).
        router: Context manager on a plan model entry; yields the endpoint
            URL (Ragas stage, ``ragas35``).
        runtime_check: Checks one plan model on a running endpoint; returns
            ``{"build", "sha256"}`` (Ragas stage).
    """

    dataset: str
    setup: str
    kind: str
    run: int
    questions: list[Any]
    layout: outputs35.Layout
    key: dict[str, Any]
    resume: bool
    trace: TraceWriter
    engine: Any = None
    settings: Any = None
    plan: Mapping[str, Any] = field(default_factory=dict)
    args: Any = None
    files: list[Path] = field(default_factory=list)
    environment: dict[str, Any] | None = None
    redact: Callable[[str], str] = _same
    tokens: Any = None
    judge: Callable[[str], Any] | None = None
    router: Callable[..., Any] | None = None
    runtime_check: Callable[..., Any] | None = None

    @property
    def factors(self) -> arms.Setup:
        """The setup's factor levels (an index stage gets ``arms.index_setup``)."""
        if self.kind == "index":
            return arms.index_setup(self.setup)
        return arms.parse_setup(self.setup)

    @property
    def index(self) -> str:
        """The index name ``e<embedder>-c<chunk>``."""
        return self.factors.index

    @property
    def collection(self) -> str:
        """The collection of this dataset and index."""
        return self.factors.collection(self.dataset)

    @property
    def index_dir(self) -> Path:
        """The ingest and seal folder of the index on this dataset."""
        return self.layout.index_dir(self.dataset, self.index)

    @property
    def run_dir(self) -> Path:
        """The folder of this repetition (search and answer stages)."""
        return self.layout.run_dir(self.dataset, self.kind, self.setup, self.run)

    @property
    def folder(self) -> Path:
        """The stage folder (``outputs35.Layout.stage_dir``)."""
        return self.layout.stage_dir(self.dataset, self.kind, self.setup, self.run)


def _error(ctx: Ctx, exc: BaseException) -> str:
    return ctx.redact(f"{type(exc).__name__}: {exc}")[:500]


def _status(error: str | None) -> str:
    return "error" if error else "ok"


# --- ingest ------------------------------------------------------------------------------


def _outcome(result: Mapping[str, Any]) -> tuple[str | None, int, list[str]]:
    """Return ``(failure, chunks, warnings)`` of one single-file ingest result."""
    details = list(result.get("file_details") or [])
    failed = result.get("status") == "error" or any(d.get("status") == "failed" for d in details)
    warnings = [str(w) for w in result.get("warnings") or []]
    if failed:
        reason = result.get("message") or "; ".join(warnings) or "ingest status error"
        return str(reason), 0, []
    chunks = sum(int(d.get("chunks") or d.get("existing_chunks") or 0) for d in details)
    return None, chunks or int(result.get("chunks_created") or 0), warnings


def _latest(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["file"]): row for row in rows}


async def ingest_stage(ctx: Ctx) -> int:
    """Ingest each corpus file on its own into the index; one row per file attempt.

    Returns:
        0 when every file is ingested (the done-marker is written).

    Raises:
        StageIncomplete: A file failed; the message names it. No marker.
    """
    with outputs35.RowFile(ctx.folder, "ingest", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[ingest] {ctx.dataset}/{ctx.setup}: done earlier, skipped")
            return 0
        done = {name for name, row in _latest(log.rows()).items() if row["status"] == "ok"}
        written = 0
        for path in ctx.files:
            if path.name in done:
                continue
            started = time.perf_counter()
            watchdog = threading.Timer(
                FILE_WATCHDOG_SECONDS, _stuck, (path.name, FILE_WATCHDOG_SECONDS)
            )
            watchdog.daemon = True
            watchdog.start()
            try:
                error, chunks, warnings = _outcome(
                    await ctx.engine.ingest(str(path), collection_name=ctx.collection)
                )
                error = ctx.redact(error)[:500] if error else None
            except Exception as exc:  # noqa: BLE001 - keep the row; --resume retries the file
                error, chunks, warnings = _error(ctx, exc), 0, []
            finally:
                watchdog.cancel()
            seconds = round(time.perf_counter() - started, 3)
            row = {
                "file": path.name,
                "status": _status(error),
                "chunks": chunks,
                "warnings": warnings,
                "error": error,
                "seconds": seconds,
            }
            log.append(row)
            written += 1
            if written % VERSION_CLEANUP_EVERY == 0:
                _drop_old_versions(ctx)
            ctx.trace.write(
                stage="ingest",
                dataset=ctx.dataset,
                question_id=path.name,
                status=_status(error),
                error=error,
                chunk_counts={"chunks_created": chunks},
                durations_s={"ingest": seconds},
            )
            say(f"[ingest] {path.name}: {'ERROR ' + error if error else f'{chunks} chunks'}")
        latest = _latest(log.rows())
        names = [p.name for p in ctx.files]
        failed = [n for n in names if latest.get(n, {}).get("status") != "ok"]
        summary = {
            "files": {n: latest[n]["chunks"] for n in names if n not in failed},
            "warnings": {
                n: latest[n]["warnings"] for n in names if latest.get(n, {}).get("warnings")
            },
            "failed": failed,
            "chunks": sum(int(latest[n]["chunks"]) for n in names if n not in failed),
        }
        outputs35.write_json(ctx.folder / "ingest-summary.json", summary)
        if failed:
            raise StageIncomplete(
                f"{len(failed)} files failed to ingest ({', '.join(failed)}); no done-marker "
                "was written. Run the stage again with --resume."
            )
        log.mark_done(summary)
    return 0


def _drop_old_versions(ctx: Ctx) -> None:
    """Delete every table version of the index but the latest.

    The rows, their order and ``table.version`` stay the same; only the version
    history goes. Safe here only: each index is built once by one process, then
    sealed, and G2 compares a rebuild (protocol section 7).
    """
    from datetime import timedelta

    import lancedb

    try:
        table = lancedb.connect(str(ctx.layout.store(ctx.index))).open_table(ctx.collection)
    except ValueError as exc:
        if "was not found" in str(exc):
            return  # nothing written yet
        raise
    table.to_lance().cleanup_old_versions(older_than=timedelta(0))


# --- seal --------------------------------------------------------------------------------


def _same_chunk_size(ctx: Ctx, mine: Mapping[str, Any]) -> list[str]:
    """Compare per-file chunk counts and warnings with the other embedders' markers."""
    compared = []
    for embedder in arms.EMBEDDERS:
        other = f"e{embedder}-c{ctx.factors.chunk}"
        path = ctx.layout.index_dir(ctx.dataset, other) / ".done-ingest.json"
        if other == ctx.index or not path.exists():
            continue
        theirs = json.loads(path.read_text(encoding="utf-8"))
        for part in ("files", "warnings"):
            a, b = mine.get(part) or {}, theirs.get(part) or {}
            for name in sorted(set(a) | set(b)):
                if a.get(name) != b.get(name):
                    raise SealRefused(
                        f"{ctx.dataset}/{ctx.index}: {name} has {part} {a.get(name)!r}, "
                        f"but {other} has {b.get(name)!r}; the three embedders of one chunk "
                        "size must chunk every file the same way"
                    )
        compared.append(other)
    return compared


def _read_index(ctx: Ctx) -> dict[str, Any]:
    """Return the table facts of the collection, read without any write."""
    import lancedb

    from omrs.core.vectordb.lancedb.fts import fts_index_stats
    from omrs.core.vectordb.lancedb.meta import read_dataset_epoch

    table = lancedb.connect(str(ctx.layout.store(ctx.index))).open_table(ctx.collection)
    fts = fts_index_stats(table)
    unpaged = (
        table.count_rows("metadata.page_label IS NULL OR metadata.page_label = ''")
        if ctx.dataset == "financebench"
        else 0
    )
    return {
        "table_version": int(table.version),
        "dataset_epoch": read_dataset_epoch(table),
        "chunks": int(table.count_rows()),
        "embedding_dimension": table.schema.field("vector").type.list_size,
        "fts": None if fts is None else {"indexed": fts[0], "unindexed": fts[1]},
        "unpaged_chunks": int(unpaged),
    }


def _write_environment(ctx: Ctx) -> None:
    path = ctx.layout.environment
    if path.exists():
        _compare_environment(json.loads(path.read_text(encoding="utf-8")), ctx.environment or {})
        return
    outputs35.write_json(path, ctx.environment)


async def seal_stage(ctx: Ctx) -> int:
    """Seal one index of one dataset: check it and write ``index-fingerprint.json``.

    The fingerprint holds the collection, table version, dataset epoch, chunk
    count, embedding dimension, the resolved sparse backend of the index's
    hybrid-on setups, the full-text index row counts (or none), the
    FinanceBench unpaged chunk count and the embedders compared. The seal also
    writes the build environment record ``environment.json`` (D19).

    Raises:
        StageOrderError: The index has no ``.done-ingest.json``.
        SealRefused: Unpaged FinanceBench chunks, a missing or stale full-text
            index under ``native``, or chunk counts or warnings that differ
            from another embedder at the same chunk size.
    """
    marker = ctx.index_dir / ".done-ingest.json"
    if not marker.exists():
        raise StageOrderError(
            f"index {ctx.index} on {ctx.dataset} has no finished ingest ({marker}); "
            "run the ingest stage first"
        )
    with outputs35.RowFile(ctx.folder, "seal", ctx.key, resume=ctx.resume) as log:
        if log.done:
            say(f"[seal] {ctx.dataset}/{ctx.index}: done earlier, skipped")
            return 0
        fingerprint = _check_index(ctx, json.loads(marker.read_text(encoding="utf-8")))
        outputs35.write_json(ctx.layout.fingerprint(ctx.dataset, ctx.index), fingerprint)
        _write_environment(ctx)
        log.mark_done(fingerprint)
    say(
        f"[seal] {fingerprint['collection']}: version {fingerprint['table_version']}, "
        f"{fingerprint['chunks']} chunks"
    )
    return 0


def _check_index(ctx: Ctx, marker: Mapping[str, Any]) -> dict[str, Any]:
    compared = _same_chunk_size(ctx, marker)
    facts = _read_index(ctx)
    backend = ctx.settings.retrieval.hybrid_sparse_backend
    where = f"{ctx.dataset}/{ctx.index} ({ctx.collection})"
    if facts["unpaged_chunks"]:
        raise SealRefused(
            f"{where} holds {facts['unpaged_chunks']} chunks with no page label; FinanceBench "
            "is scored by page, so rebuild the index after fixing the PDF reader path"
        )
    if backend == "native" and (facts["fts"] is None or facts["fts"]["unindexed"]):
        found = (
            "no full-text index"
            if facts["fts"] is None
            else (f"a full-text index with {facts['fts']['unindexed']} unindexed rows")
        )
        raise SealRefused(f"{where} resolves sparse backend native but has {found}")
    return {
        "dataset": ctx.dataset,
        "index": ctx.index,
        "collection": ctx.collection,
        "sparse_backend": backend,
        "compared_with": compared,
        **facts,
    }


# --- machine and environment record ------------------------------------------------------


def check_machine(machine: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    """Refuse a machine with no GPU model or image, or an image other than the plan pin.

    The image must be ``plan.json`` ``pins.environment.image`` exactly (task 9.1).

    Raises:
        EnvironmentMismatch: The message names the field.
    """
    for name in ("gpu", "image"):
        if not machine.get(name):
            raise EnvironmentMismatch(
                f"the environment record has no {name} (nvidia-smi and EXP35_POD_IMAGE); "
                "every model stage runs on the pinned pod (design D19)"
            )
    if "@sha256:" not in str(machine["image"]):
        raise EnvironmentMismatch(
            f"EXP35_POD_IMAGE {machine['image']!r} has no @sha256: digest; pin the image by digest"
        )
    pinned = arms.pinned(plan, "pins", "environment", "image", error=EnvironmentMismatch)
    if machine["image"] != pinned:
        raise EnvironmentMismatch(
            f"EXP35_POD_IMAGE {machine['image']!r} is not plan.json pins.environment.image "
            f"{pinned!r}; create the pod from the pinned image (task 9.1)"
        )


def environment_record(machine: Mapping[str, Any], found: Any) -> dict[str, Any]:
    """Return the environment record: GPU, image, llama.cpp build and checked GGUF SHA-256."""
    return {
        "gpu": machine.get("gpu"),
        "image": machine.get("image"),
        "llama_cpp_build": found.build,
        "gguf_sha256": {m["file"]: m["sha256"] for m in found.models},
    }


def _compare_environment(built: Mapping[str, Any], mine: Mapping[str, Any]) -> None:
    for name in ENV_FIELDS[:3]:
        if built.get(name) != mine.get(name):
            raise EnvironmentMismatch(
                f"environment field {name} is {mine.get(name)!r} here and {built.get(name)!r} "
                "in environment.json; every stage runs in the build environment"
            )
    shared = set(built.get("gguf_sha256") or {}) & set(mine.get("gguf_sha256") or {})
    for file in sorted(shared):
        if built["gguf_sha256"][file] != mine["gguf_sha256"][file]:
            raise EnvironmentMismatch(f"environment field gguf_sha256 differs for {file}")


def record_machine(ctx: Ctx, machine: Mapping[str, Any], environment: Mapping[str, Any]) -> None:
    """Compare the stage's environment with ``environment.json``; append its machine line.

    An index stage may run before the first seal writes the build record; a
    search or answer stage refuses without it.

    Raises:
        EnvironmentMismatch: A field differs, or the build record is missing for
            a search or answer stage. Nothing is appended.
    """
    path = ctx.layout.environment
    if path.exists():
        _compare_environment(json.loads(path.read_text(encoding="utf-8")), environment)
    elif ctx.kind != "index":
        raise EnvironmentMismatch(f"{path} is missing; seal the index before this stage runs")
    line = {
        "host": machine.get("host"),
        "pod_id": machine.get("pod_id"),
        "environment": environment,
    }
    ctx.folder.mkdir(parents=True, exist_ok=True)
    with (ctx.folder / "machine.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")
