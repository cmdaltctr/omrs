"""Search-cost figure data of Experiment 35 (task 14.4; pre-registration section 14.3).

Usage (reads saved files only; runs on the Mac)::

    searchcost35.py --out-dir OUT --halves HALVES [--ragflow-scores DIR]

The figure shows the expected maximum of the pooled half-A nDCG@10 over n
setups drawn at random without replacement (adapted from Dodge et al. 2019),
computed exactly by ``select35.expected_max_curve`` on the scores sorted in
ascending order. The pooled score is the plain mean of the per-dataset half-A
means over the three core datasets, as in the selection rule (section 14.1).

Curves (data only; drawing the figure is left to the report):

- ``a3_cells``: the 12 cells of the chosen embedder and reranker size
  (``selection.json`` ``cell_scores``), n = 1 to 12;
- ``all_setups``: the 72 search setups, n = 1 to 72;
- ``ragflow``: RAGFlow's own half-A cells, only when its matched search ran
  (section 18); otherwise ``null`` with a note.

Writes ``<out>/search-cost.json``. Every score is a half-A score, so the file
needs no half-B guard.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import select35  # noqa: E402
import split35  # noqa: E402
from outputs35 import write_json  # noqa: E402

A3_CELLS = 12
NO_RAGFLOW = "RAGFlow matched search did not run: no RAGFlow curve (section 18)"


def _curve(scores: Mapping[str, float]) -> dict[str, Any]:
    names = sorted(scores)
    return {
        "setups": names,
        "scores": {s: scores[s] for s in names},
        "n": list(range(1, len(names) + 1)),
        "expected_max": select35.expected_max_curve([scores[s] for s in names]),
    }


def _pooled_any(
    records: Iterable[Mapping[str, Any]], halves: Mapping[str, Mapping[str, str]]
) -> dict[str, float]:
    """Return the pooled half-A nDCG@10 of every setup in *records* (RAGFlow cell names).

    Raises:
        select35.SelectionError: A setup lacks a score for a half-A question; names both.
    """
    wanted = {d: {q for q, h in halves[d].items() if h == "A"} for d in select35.CORE}
    found: dict[str, dict[str, dict[str, float]]] = {}
    for row in records:
        dataset, qid = row["dataset"], str(row["qid"])
        if dataset in wanted and qid in wanted[dataset] and row.get(select35.NDCG) is not None:
            per = found.setdefault(row["setup"], {}).setdefault(dataset, {})
            per[qid] = float(row[select35.NDCG])
    pooled = {}
    for setup in sorted(found):
        means = []
        for dataset in select35.CORE:
            scores = found[setup].get(dataset, {})
            missing = wanted[dataset] - set(scores)
            if missing:
                raise select35.SelectionError(
                    f"setup {setup} on {dataset} lacks {len(missing)} half-A scores"
                    f" (for example {sorted(missing)[0]})"
                )
            means.append(math.fsum(scores[q] for q in sorted(scores)) / len(scores))
        pooled[setup] = math.fsum(means) / len(means)
    return pooled


def search_cost(
    records: Iterable[Mapping[str, Any]],
    halves: Mapping[str, Mapping[str, str]],
    selection: Mapping[str, Any],
    ragflow_records: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the search-cost curves from pooled half-A scores.

    Args:
        records: OMRS per-question search score records (72 setups).
        halves: Per dataset, the half of each question ID.
        selection: The ``selection.json`` content; its ``cell_scores`` name the 12 A3 cells.
        ragflow_records: RAGFlow per-question search score records, only when the
            matched RAGFlow search ran; ``None`` otherwise.

    Raises:
        select35.SelectionError: A setup lacks a half-A score, or the selection
            does not name 12 cells.
    """
    means = select35.half_a_means(records, halves)
    pooled = {s: math.fsum(means[s][d] for d in select35.CORE) / 3 for s in select35.SEARCH_SETUPS}
    cells = list(selection["cell_scores"])
    if len(cells) != A3_CELLS or not set(cells) <= set(pooled):
        raise select35.SelectionError(
            f"selection names {len(cells)} A3 cells of the grid; the figure needs {A3_CELLS}"
        )
    flow = None if ragflow_records is None else _curve(_pooled_any(ragflow_records, halves))
    return {
        "metric": select35.NDCG,
        "half": "A",
        "estimator": "exact expected maximum, without replacement (adapted from Dodge et al. 2019)",
        "a3_cells": _curve({s: pooled[s] for s in cells}),
        "all_setups": _curve(pooled),
        "ragflow": flow,
        "ragflow_note": NO_RAGFLOW if flow is None else "RAGFlow matched search ran",
    }


def _read_dir(folder: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted(folder.glob("*/*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<out>/search-cost.json``; return 0, or 2 when the saved scores are refused."""
    parser = argparse.ArgumentParser(prog="searchcost35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the run output folder")
    parser.add_argument("--halves", type=Path, required=True, help="the halves.json file")
    parser.add_argument(
        "--ragflow-scores",
        type=Path,
        help="half-A RAGFlow score folder (<dataset>/<cell>.jsonl); only if its matched search ran",
    )
    args = parser.parse_args(argv)
    try:
        selection = json.loads((args.out_dir / "selection.json").read_text(encoding="utf-8"))
        flow = None if args.ragflow_scores is None else _read_dir(args.ragflow_scores)
        data = search_cost(
            _read_dir(args.out_dir / "scores" / "A"),
            split35.read_halves(args.halves),
            selection,
            flow,
        )
    except (select35.SelectionError, OSError) as error:
        print(f"[error] {error}", flush=True)
        return 2
    write_json(args.out_dir / "search-cost.json", data)
    print(f"[search-cost] {args.out_dir / 'search-cost.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
