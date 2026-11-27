"""Pooled H8 estimate of Experiment 35 (A18; pre-registration section 9 point 7).

Rows 12 to 19 get one inverse-variance-weighted mean of the FinanceBench and
FreshStack estimates, weight = 1 / variance. FreshStack takes the bias-reduced
GEE variance of point 3. FinanceBench takes the document-cluster GEE variance
of point 6. The 95% interval uses a normal reference. A row not testable on
either dataset is not pooled. A row whose two estimates have opposite signs is
marked ``signs_differ``. The pooled row is secondary: it is printed beside the
per-dataset estimates, reads against no SESOI and changes no verdict.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import factorial35
from cells35 import cell_means, contrast, documents
from experiments._lib import stats_cluster

DATASETS = (factorial35.FB, factorial35.FS)
POOLED_ROWS = tuple(r for r in factorial35.ROWS if r.number >= 12)
Z_95 = 1.959963984540054  # the 97.5th percentile of the standard normal


def _unpooled(row: factorial35.Row, reason: str, per: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row": row.number,
        "pooled": False,
        "reason": reason,
        "estimate": None,
        "variance": None,
        "ci_low": None,
        "ci_high": None,
        "signs_differ": False,
        "per_dataset": dict(per),
        "decides_nothing": True,
    }


def _status(rows: Sequence[Mapping[str, Any]] | None, number: int) -> str | None:
    """Return why row *number* is not testable in a dataset's saved rows, else None."""
    found = next((r for r in rows or () if r["row"] == number), None)
    if found is None:
        return "no row"
    if found.get("dropped"):
        return "dropped"
    return "gated" if found.get("not_testable") else None


def _estimate(
    row: factorial35.Row, dataset: str, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | str:
    """Return the dataset's estimate, variance and n; a string says why it has none."""
    metric = factorial35.endpoint(row, dataset)
    cells = cell_means([r for r in records if r["dataset"] == dataset], metric).get(dataset, {})
    d, _ = contrast(row, cells)
    qids = sorted(d)
    if len(qids) < 2:
        return "fewer than 2 questions"
    clusters = None
    if dataset == factorial35.FB:  # point 6: document clusters
        docs = documents(records).get(dataset, {})
        clusters = [docs[q] for q in qids]
    test = stats_cluster.cluster_test([d[q] for q in qids], clusters=clusters)
    if not test.variance > 0:  # also NaN
        return "variance not positive"
    return {
        "estimate": math.fsum(d.values()) / len(d),
        "variance": test.variance,
        "n": len(qids),
    }


def pooled_h8(
    answer_records: Sequence[Mapping[str, Any]],
    rows_by_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[int, dict[str, Any]]:
    """Return the pooled H8 estimate of rows 12 to 19, keyed by row number.

    Args:
        answer_records: The per-question answer score records (``factorial35``).
        rows_by_dataset: Each dataset's saved confirmatory rows. A row marked
            ``not_testable`` or ``dropped`` there, or a missing row, is not
            testable and is not pooled.

    Returns:
        Per row: ``pooled``, ``estimate``, ``variance``, ``ci_low``, ``ci_high``,
        ``signs_differ``, the ``per_dataset`` estimates, ``reason`` (when not
        pooled) and ``decides_nothing``. No p-value is given.
    """
    out: dict[int, dict[str, Any]] = {}
    for row in POOLED_ROWS:
        per: dict[str, Any] = {}
        reason = ""
        for dataset in DATASETS:
            why = _status(rows_by_dataset.get(dataset), row.number)
            found = why or _estimate(row, dataset, answer_records)
            if isinstance(found, str):
                reason = reason or f"not testable on {dataset}: {found}"
            else:
                per[dataset] = found
        if reason:
            out[row.number] = _unpooled(row, reason, per)
            continue
        weights = {d: 1 / per[d]["variance"] for d in DATASETS}
        total = sum(weights.values())
        estimate = sum(weights[d] * per[d]["estimate"] for d in DATASETS) / total
        half = Z_95 * math.sqrt(1 / total)
        signs = [per[d]["estimate"] for d in DATASETS]
        out[row.number] = {
            "row": row.number,
            "pooled": True,
            "estimate": estimate,
            "variance": 1 / total,
            "ci_low": estimate - half,
            "ci_high": estimate + half,
            "signs_differ": signs[0] * signs[1] < 0,
            "per_dataset": per,
            "decides_nothing": True,
        }
    return out
