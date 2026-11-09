"""Estimates from timing rows and token counts, and atomic output writes.

Shared copy of the Experiment 48 helpers (``timing_lib.py`` and the timing
functions of ``sweep_lib.py``). Pure: the runner reads and writes the files. A
row or count that came from a ``--limit`` run, or a row that recorded an
error, is refused: it would understate the hours of the full corpora.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


class LimitMismatchError(RuntimeError):
    """A resumed artefact came from a run with a different ``--limit``."""


def require_same_limit(recorded: int | None, current: int | None, what: str) -> None:
    """Refuse to reuse *what* when its ``--limit`` differs from this run's.

    A smoke run (``--limit 1``) writes the same markers and files as a full
    run. Without this check a later ``--resume`` skips the stage and reports
    the full run complete.

    Args:
        recorded: The ``limit`` stored with the artefact (``None`` for a full run).
        current: The ``--limit`` of this run (``None`` for a full run).
        what: Name of the artefact, for the message.

    Raises:
        LimitMismatchError: The two limits differ. Names both and the fix.
    """
    if recorded != current:
        raise LimitMismatchError(
            f"{what} came from a run with --limit {recorded}; this run has --limit {current}. "
            "Move the old output and the scratch index aside, then run again."
        )


def extrapolate(
    *,
    tokens_per_second: float,
    corpus_tokens: int | None = None,
    tokens_per_page: float | None = None,
    total_pages: int | None = None,
    corpus: str | None = None,
) -> float:
    """Estimate embedding hours for one corpus from a measured rate.

    Either pass the corpus token count, or tokens per page times total pages.
    """
    if corpus_tokens is None:
        if tokens_per_page is None or total_pages is None:
            name = corpus or "this corpus"
            raise ValueError(f"{name}: token count missing; pass corpus_tokens or page figures")
        corpus_tokens = int(tokens_per_page * total_pages)
    return corpus_tokens / tokens_per_second / 3600.0


def speed_summary(
    exact: Mapping[str, Mapping[str, float]], fast: Mapping[str, Mapping[str, float]]
) -> dict[str, dict[str, float]]:
    """Vectors per second of each mode and the gain, per slice (design D6a step 5).

    Args:
        exact: Slice name to ``{"seconds", "vectors"}`` for exact mode.
        fast: The same for fast mode.

    Raises:
        ValueError: The two modes did not time the same slices.
    """
    if set(exact) != set(fast):
        raise ValueError(
            f"exact timed {sorted(exact)} but fast timed {sorted(fast)}; "
            "run both modes on the same slices"
        )
    summary = {}
    for name in sorted(exact):
        slow = exact[name]["vectors"] / exact[name]["seconds"]
        quick = fast[name]["vectors"] / fast[name]["seconds"]
        summary[name] = {
            "exact_vectors_per_second": slow,
            "fast_vectors_per_second": quick,
            "speed_gain": quick / slow,
        }
    return summary


def estimates(
    counts: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    financebench_slice_pages: int,
) -> dict[str, Any]:
    """Return hours per corpus and peak memory, one entry per model.

    Args:
        counts: The parsed ``token-counts.json``.
        rows: Every timing row of every model.
        financebench_slice_pages: Pages of the FinanceBench PDFs the timing slice embedded.

    Raises:
        LimitMismatchError: The counts or a row came from a ``--limit`` run.
        ValueError: A row recorded errors, or *financebench_slice_pages* is not positive.
    """
    if financebench_slice_pages <= 0:
        raise ValueError("FinanceBench slice pages must be above zero")
    require_same_limit(counts.get("limit"), None, "token-counts.json")
    timing: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        what = f"timing row {row['model']}/{row['slice']}"
        require_same_limit(row.get("limit"), None, what)
        if row.get("errors"):
            raise ValueError(
                f"{what} recorded errors ({'; '.join(row['errors'])}); rerun the slice"
            )
        timing[(row["model"], row["slice"])] = row
    rates: dict[str, dict[str, float]] = {}
    for (model, slice_name), row in timing.items():
        rates.setdefault(model, {})[slice_name] = row["tokens_per_second"]
    fb_slice = timing.get(("4b", "financebench"))
    result = {}
    for model, per_slice in rates.items():
        fb_rate = per_slice.get("financebench", fb_slice["tokens_per_second"] if fb_slice else 0)
        fb_row = timing.get((model, "financebench")) or fb_slice
        tokens_per_page = None
        if fb_row and counts["financebench"]["total_pages"]:
            tokens_per_page = fb_row["tokens"] / financebench_slice_pages
        result[model] = {
            "freshstack_hours": extrapolate(
                corpus_tokens=counts["freshstack"]["tokens"],
                tokens_per_second=per_slice["freshstack"],
            ),
            "bioasq_hours": extrapolate(
                corpus_tokens=counts["bioasq"]["tokens"], tokens_per_second=per_slice["bioasq"]
            ),
            "financebench_hours": extrapolate(
                tokens_per_second=fb_rate,
                tokens_per_page=tokens_per_page,
                total_pages=counts["financebench"]["total_pages"],
            ),
            "peak_rss_mb": {
                slice_name: row["peak_rss_mb"]
                for (name, slice_name), row in timing.items()
                if name == model
            },
        }
    return result


def read_speed(output: Path, mode: str) -> dict[str, Any]:
    """Read the per-slice seconds and vector counts that one Part C mode wrote.

    Raises:
        SystemExit: The file is missing; the message names it and the stage to rerun.
    """
    path = output / f"part-c-{mode}-speed.json"
    if not path.is_file():
        raise SystemExit(
            f"{path.name} is missing: run --part-c --stage {mode} again; "
            "it now records the speed of the mode"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write *rows* to *path*, one JSON object per line, atomically.

    The rows go to a temporary file in the same folder, which then replaces
    *path*. A write that stops part-way leaves the old file, or no file, and no
    temporary file.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path: Path, value: Any) -> None:
    """Write *value* to *path* as indented JSON, atomically (see :func:`write_jsonl`)."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
