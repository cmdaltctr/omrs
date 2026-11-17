"""Minimum detectable effects of Experiment 35 (pre-registration section 10, task 15.11).

Works on saved score records only (the same record shape as ``factorial35.py``).
MDE = (z at 1 minus alpha/2 plus z at 0.80) x SD / square root of n, with
alpha = 0.05 / family size (19 on FinanceBench and FreshStack, 8 on BioASQ)
and, on FinanceBench, n divided by the design effect of document clustering.
n is the main-run question count of the dataset. The SD is the sample SD of
the per-question contrast scores of the pilot (retrieval rows) or of the named
smoke and test-pod answer files (answer rows, labelled rough). An adjacent-level
row uses the extreme-level contrast as a stand-in and says so.
"""

from __future__ import annotations

import json
import os
import statistics
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import factorial35
import select35
from experiments._lib import stats_cluster
from experiments._lib.stats_d6 import min_detectable_effect

FB, FS, BQ = select35.CORE
QUESTIONS = {FB: 150, FS: 203, BQ: 707}
FAMILY_SIZE = {FB: 19, FS: 19, BQ: 8}
SESOI = 0.02
POWER = 0.8
ASSUMED_SD = (0.15, 0.25)
PILOT_ROWS = {FB: range(1, 12), FS: range(1, 12), BQ: range(1, 9)}


def _extreme(factor: str, high: Any, low: Any) -> Any:
    return ((1.0, {factor: (high,)}), (-1.0, {factor: (low,)}))


STAND_INS = {
    1: (_extreme("embedder", "8b", "0.6b"), "e8b minus e0.6b"),
    2: (_extreme("embedder", "8b", "0.6b"), "e8b minus e0.6b"),
    7: (_extreme("reranker", "8b", "0.6b"), "r8b minus r0.6b"),
    8: (_extreme("reranker", "8b", "0.6b"), "r8b minus r0.6b"),
    9: (_extreme("chunk", 2048, 512), "c2048 minus c512"),
    10: (_extreme("chunk", 2048, 512), "c2048 minus c512"),
}


def design_effect(d: Sequence[float], documents: Sequence[str]) -> float:
    """Return the document-cluster variance of the mean over its question-level variance.

    Both variances are the bias-reduced closed form of ``stats_cluster``.
    """
    clustered = stats_cluster.closed_form(d, documents)[1]
    return clustered / stats_cluster.closed_form(d)[1]


def mde_row(
    dataset: str,
    row: int,
    sd: float,
    *,
    source: str,
    design_effect: float | None = None,
    stand_in: str | None = None,
    rough: bool = False,
    pilot_n: int | None = None,
) -> dict[str, Any]:
    """Return one MDE table row.

    Args:
        dataset: Core dataset name.
        row: Contrast table row (section 8).
        sd: SD of the per-question contrast scores.
        source: Where the SD comes from.
        design_effect: FinanceBench design effect; None leaves n undivided. A value
            below 1 is floored at 1 before n is divided; the row keeps the raw value.
        stand_in: The extreme-level contrast used for an adjacent-level row.
        rough: True for answer-stage rows from smoke and test-pod files.
        pilot_n: Questions behind the SD.

    Returns:
        The row, with the MDE and its reading against the SESOI (nDCG@10 only).
    """
    metric = factorial35.endpoint(factorial35.ROWS[row - 1], dataset)
    n = QUESTIONS[dataset]
    n_effective = n if design_effect is None else n / max(1.0, design_effect)
    alpha = 0.05 / FAMILY_SIZE[dataset]
    mde = min_detectable_effect(sd, n_effective, alpha=alpha, power=POWER)
    on_ndcg = metric == factorial35.NDCG
    return {
        "dataset": dataset,
        "row": row,
        "metric": metric,
        "sd": sd,
        "sd_source": source,
        "pilot_n": pilot_n,
        "stand_in": stand_in,
        "rough": rough,
        "assumed": False,
        "design_effect": design_effect,
        "n": n,
        "n_effective": n_effective,
        "alpha": alpha,
        "mde": mde,
        "sesoi": SESOI if on_ndcg else None,
        "below_sesoi": mde <= SESOI if on_ndcg else None,
    }


def _entry(
    dataset: str,
    number: int,
    terms: Any,
    records: Sequence[Mapping[str, Any]],
    *,
    source: str,
    stand_in: str | None,
    rough: bool,
) -> dict[str, Any]:
    base = factorial35.ROWS[number - 1]
    row = factorial35.Row(
        number, base.hypothesis, base.stage, base.outcome, terms, base.directional
    )
    metric = factorial35.endpoint(base, dataset)
    cells = factorial35.cell_means(records, metric).get(dataset, {})
    universe = [
        s
        for s in cells
        if base.stage == "search" or select35.parse_setup(s).t20k == (base.stage == "t20k")
    ]
    for _, levels in terms:
        if not any(
            all(getattr(select35.parse_setup(s), k) in v for k, v in levels.items())
            for s in universe
        ):
            raise ValueError(f"row {number} on {dataset}: no saved cell matches {dict(levels)}")
    d, _ = factorial35.contrast(row, cells)
    qids = sorted(d)
    values = [d[q] for q in qids]
    effect = None
    if dataset == FB:
        docs = {str(r["qid"]): str(r["doc_id"]) for r in records if r["dataset"] == FB}
        effect = design_effect(values, [docs[q] for q in qids])
    return mde_row(
        dataset,
        number,
        statistics.stdev(values),
        source=source,
        design_effect=effect,
        stand_in=stand_in,
        rough=rough,
        pilot_n=len(values),
    )


def pilot_table(
    records: Iterable[Mapping[str, Any]], source: str = "pilot"
) -> list[dict[str, Any]]:
    """Return the retrieval rows of the MDE table from saved pilot search records.

    Raises:
        ValueError: The pilot holds no cell for a term of a row; names the row.
    """
    rows = list(records)
    table = []
    for dataset, numbers in PILOT_ROWS.items():
        for number in numbers:
            terms, stand_in = STAND_INS.get(number, (factorial35.ROWS[number - 1].terms, None))
            table.append(
                _entry(dataset, number, terms, rows, source=source, stand_in=stand_in, rough=False)
            )
    return table


def answer_table(records: Iterable[Mapping[str, Any]], source: str) -> list[dict[str, Any]]:
    """Return the answer rows (12 to 19) from saved smoke and test-pod answer records, rough.

    Only FinanceBench and FreshStack hold these rows in a family.
    """
    rows = list(records)
    present = {r["dataset"] for r in rows}
    return [
        _entry(d, k, factorial35.ROWS[k - 1].terms, rows, source=source, stand_in=None, rough=True)
        for d in (FB, FS)
        if d in present
        for k in range(12, 20)
    ]


def assumed_table() -> list[dict[str, Any]]:
    """Return the registered fallback: retrieval rows from assumed SDs 0.15 to 0.25.

    No design effect is measured, so FinanceBench n is not divided.
    """
    table = []
    for dataset, numbers in PILOT_ROWS.items():
        for number in numbers:
            low = mde_row(dataset, number, ASSUMED_SD[0], source="assumed")
            high = mde_row(dataset, number, ASSUMED_SD[1], source="assumed")
            table.append(
                {
                    **low,
                    "assumed": True,
                    "sd": None,
                    "sd_low": ASSUMED_SD[0],
                    "sd_high": ASSUMED_SD[1],
                    "mde": None,
                    "mde_low": low["mde"],
                    "mde_high": high["mde"],
                    "below_sesoi": None,
                }
            )
    return table


def write_table(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write the MDE table atomically as JSON."""
    body = {"sesoi": SESOI, "power": POWER, "rows": list(rows)}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
