"""Estimates from timing rows and token counts (change task 5.4, review fixes 2026-11-08).

Pure: the runner reads and writes the files. A row or count that came from a
``--limit`` run, or a row that recorded an error, is refused: it would
understate the hours of the full corpora.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sweep_lib import extrapolate, require_same_limit


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
