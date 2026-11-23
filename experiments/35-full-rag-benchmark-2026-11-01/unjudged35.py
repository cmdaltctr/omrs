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

Score records are those of ``score35.py`` (``dataset``, ``setup``, ``qid`` and
``units``, the top 10 units in rank order). Qrels map each question to its
judged units and their grade. This module computes the trigger values only;
the audit sample and page (seed 20261120) are built only if it fires.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import select35

DEPTH = 10
GAP = 0.05
TOLERANCE = 1e-9  # a gap of exactly 5 points must not fire through float error
FRESHSTACK = "freshstack"
NOT_DEFINED = "qrels hold positives only: unjudged share not defined, trigger not used"
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
