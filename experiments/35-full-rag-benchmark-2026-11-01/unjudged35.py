"""Unjudged share and blind-audit trigger of Experiment 35 (task 16.25; PR 11.3 and 21).

O3 (decided by the owner on 2026-11-14): no blind relevance audit by default.
The audit runs only if this trigger fires: the mean unjudged share in the top
10 units differs by more than 5 percentage points (0.5 units per question)

- (a) between hybrid on and hybrid off on FreshStack, marginal over the other
  factors (:func:`hybrid_trigger`, all questions, after step 5 of section 14.2);
- (b) between OMRS and RAGFlow on any core dataset in Part 2
  (:func:`system_trigger`, after the Part 2 runs).

A unit is unjudged when the qrels of its question hold no judgement for it; a
placeholder unit (an unmapped chunk) has none, so it counts as unjudged. The
share divides by the 10 ranks: a short list's missing ranks hold no unit. The
trigger is defined only on a dataset whose qrels list judged non-relevant
units (a judgement of 0 or less); on a positives-only dataset the share cannot
be told apart from retrieval quality, so nothing is computed there. The gap is
absolute, so it is blind to which side scores higher.

Score records are those of ``score35.py`` (``dataset``, ``setup``, ``qid``,
``units``, the top 10 units in rank order, and ``ranked_units``, every distinct
unit in rank order). Qrels map each question to its judged units and their
grade (``datasets35.qrels``). The audit sample and page (seed 20261120) are
built only if the trigger fires.

Condensed-list nDCG@10 (Sakai 2007; pre-registration section 21, RDY 16.4) is
the sensitivity of rows 1 to 8 (H1 to H5): each ranked list loses its unjudged
units, then nDCG@10 is taken on what is left, with the same binary gain and
ideal list as the primary score. It is descriptive: each row gives its
estimate and 95% interval by the section 9 method, beside the primary nDCG@10
estimate, and changes no decision. On a positives-only dataset the report
states that neither it nor the unjudged share can be computed as defined.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import cells35
import factorial35
import select35
from experiments._lib.retrieval_metrics import ndcg_at_k

DEPTH = 10
GAP = 0.05
TOLERANCE = 1e-9  # a gap of exactly 5 points must not fire through float error
FRESHSTACK = "freshstack"
NOT_DEFINED = "qrels hold positives only: unjudged share not defined, trigger not used"
NEITHER = (
    "qrels hold positives only: neither the unjudged share nor condensed-list nDCG@10 "
    "can be computed as defined"
)
CONDENSED = "ndcg_at_10_condensed"
#: Rows 1 to 8 of the contrast table: H1 to H5 (pre-registration section 21).
CONDENSED_ROWS = factorial35.ROWS[:8]
Qrels = Mapping[str, Mapping[str, int]]


def has_negatives(qrels: Qrels) -> bool:
    """Return True when the qrels list at least one judged non-relevant unit."""
    return any(grade <= 0 for per in qrels.values() for grade in per.values())


def unjudged_share(units: Sequence[str], judged: Mapping[str, int]) -> float:
    """Return the share of the 10 ranks that hold a unit with no judgement."""
    return sum(1 for unit in units[:DEPTH] if unit not in judged) / DEPTH


def _setup_means(records: Iterable[Mapping[str, Any]], dataset: str, qrels: Qrels) -> dict:
    shares: dict[str, list[float]] = {}
    for row in records:
        if row["dataset"] == dataset:
            judged = qrels.get(str(row["qid"]), {})
            shares.setdefault(row["setup"], []).append(unjudged_share(row["units"], judged))
    return {s: math.fsum(v) / len(v) for s, v in sorted(shares.items())}


def share_table(
    records: Iterable[Mapping[str, Any]], qrels: Mapping[str, Qrels]
) -> dict[str, dict[str, float]]:
    """Return per dataset and setup the mean unjudged share; positives-only datasets left out."""
    rows = list(records)
    return {d: _setup_means(rows, d, q) for d, q in sorted(qrels.items()) if has_negatives(q)}


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return math.fsum(items) / len(items)


def _verdict(dataset: str, left: str, right: str, a: float | None, b: float | None) -> dict:
    gap = None if a is None or b is None else abs(a - b)
    return {
        "dataset": dataset,
        "defined": gap is not None,
        left: a,
        right: b,
        "gap": gap,
        "fires": gap is not None and gap > GAP + TOLERANCE,
    }


def hybrid_trigger(records: Iterable[Mapping[str, Any]], qrels: Qrels) -> dict[str, Any]:
    """Return trigger (a): hybrid on against off on FreshStack, marginal over the other factors.

    Args:
        records: Search score records of every setup (other datasets are skipped).
        qrels: FreshStack qrels: per question, the judged units and their grade.
    """
    if not has_negatives(qrels):
        out = _verdict(FRESHSTACK, "hybrid_on", "hybrid_off", None, None)
        return {**out, "note": NOT_DEFINED}
    means = _setup_means(records, FRESHSTACK, qrels)
    by_level = {
        level: _mean(m for s, m in means.items() if select35.parse_setup(s).hybrid == level)
        for level in select35.HYBRIDS
    }
    return _verdict(FRESHSTACK, "hybrid_on", "hybrid_off", by_level["on"], by_level["off"])


def system_trigger(
    omrs_records: Iterable[Mapping[str, Any]],
    ragflow_records: Iterable[Mapping[str, Any]],
    qrels: Mapping[str, Qrels],
) -> dict[str, Any]:
    """Return trigger (b): OMRS against RAGFlow per core dataset (Part 2), and ``fires`` overall.

    Each side's share is its mean over its setups (one selected cell per system in Part 2).
    """
    omrs, flow = list(omrs_records), list(ragflow_records)
    out: dict[str, Any] = {}
    for dataset in select35.CORE:
        judged = qrels.get(dataset, {})
        if not has_negatives(judged):
            out[dataset] = {**_verdict(dataset, "omrs", "ragflow", None, None), "note": NOT_DEFINED}
            continue
        a = _setup_means(omrs, dataset, judged)
        b = _setup_means(flow, dataset, judged)
        if not a or not b:
            out[dataset] = _verdict(dataset, "omrs", "ragflow", None, None)
            continue
        out[dataset] = _verdict(dataset, "omrs", "ragflow", _mean(a.values()), _mean(b.values()))
    out["fires"] = any(out[d]["fires"] for d in select35.CORE)
    return out


def condensed_ndcg(ranked: Sequence[str], judged: Mapping[str, int]) -> float:
    """Return nDCG@10 of *ranked* after its unjudged units are removed (Sakai 2007)."""
    relevant = {unit for unit, grade in judged.items() if grade > 0}
    return ndcg_at_k([unit for unit in ranked if unit in judged], relevant, DEPTH)


def condensed_rows(
    records: Iterable[Mapping[str, Any]], qrels: Mapping[str, Qrels]
) -> dict[str, dict[str, Any]]:
    """Return per dataset with judged negatives the rows 1 to 8 on condensed-list nDCG@10.

    Each row holds the contrast estimate and its 95% interval and p-value by the
    section 9 method (all questions, as in ``factorial35.analyse``), with the
    primary nDCG@10 estimate of the same row beside it (``plain_estimate``).
    """
    rows = list(records)
    out: dict[str, dict[str, Any]] = {}
    for dataset, judged in sorted(qrels.items()):
        if not has_negatives(judged):
            continue
        mine = [r for r in rows if r["dataset"] == dataset]
        scored = [
            {**r, CONDENSED: condensed_ndcg(r["ranked_units"], judged.get(str(r["qid"]), {}))}
            for r in mine
        ]
        condensed = cells35.cell_means(scored, CONDENSED).get(dataset, {})
        plain = cells35.cell_means(mine, factorial35.NDCG).get(dataset, {})
        table = []
        for row in CONDENSED_ROWS:
            d, _ = cells35.contrast(row, condensed)
            base, _ = cells35.contrast(row, plain)
            # factorial35._test is the section 9 method of the primary rows.
            test = factorial35._test(dataset, d, {}, 0)
            plain_test = factorial35._test(dataset, base, {}, 0)
            table.append(
                {
                    "row": row.number,
                    "hypothesis": row.hypothesis,
                    "metric": CONDENSED,
                    "n": len(d),
                    **test,
                    "plain_estimate": plain_test["estimate"],
                }
            )
        out[dataset] = {"defined": True, "rows": table}
    return out


def report(records: Iterable[Mapping[str, Any]], qrels: Mapping[str, Qrels]) -> dict[str, Any]:
    """Return the section 21 table per dataset: unjudged share and condensed rows, or NEITHER."""
    rows = list(records)
    shares = share_table(rows, qrels)
    condensed = condensed_rows(rows, qrels)
    return {
        dataset: {
            "defined": True,
            "unjudged_share": shares[dataset],
            "condensed_ndcg_rows": condensed[dataset]["rows"],
        }
        if dataset in condensed
        else {"defined": False, "note": NEITHER}
        for dataset in sorted(qrels)
    }
