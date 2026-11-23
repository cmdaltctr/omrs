"""Missing-outcome bounds of Experiment 35 (task 16.20, A5 item 57; pre-registration section 12).

Registered sensitivity analyses, never decisive. Each variant changes one kind
of missing outcome into a value, then runs the answer rows of its outcome again
with the registered test of section 9 (``factorial35``):

- ``no_claim_scored_1`` and ``no_claim_scored_0``: a run with no faithfulness
  value that is not unjudged (an answer with no factual claim, or a missing
  answer) scores 1, or 0 (rows 12, 13, 16 and 17);
- ``unjudged_scored_0``: a run whose checker row closed missing scores 0 for
  faithfulness (rows 12, 13, 16 and 17);
- ``correctness_unjudged_or_not_defined_scored_0``: a run whose Ragas
  correctness closed missing (``unjudged``) or returned no defined score
  (``not_defined``) scores 0 (rows 14, 15, 18 and 19).

Records are the ``factorial35`` answer score records (``join35.py``
``answer-scores.jsonl``). The records passed in are never changed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import factorial35
from experiments._lib import stats_cluster

FAITH, CORRECT = factorial35.FAITH, factorial35.CORRECT
ROWS = {FAITH: (12, 13, 16, 17), CORRECT: (14, 15, 18, 19)}
#: Variant name: (metric, value given, kind of missing outcome changed).
VARIANTS = {
    "no_claim_scored_1": (FAITH, 1.0, "no_claim"),
    "no_claim_scored_0": (FAITH, 0.0, "no_claim"),
    "unjudged_scored_0": (FAITH, 0.0, "unjudged"),
    "correctness_unjudged_or_not_defined_scored_0": (CORRECT, 0.0, "unjudged_or_not_defined"),
}


def _changed(row: Mapping[str, Any], metric: str, value: float, kind: str) -> dict[str, Any]:
    out = dict(row)
    unjudged = list(row.get("unjudged") or ())
    undefined = list(row.get("not_defined") or ())
    if kind == "no_claim":
        if row.get(metric) is None and metric not in unjudged:
            out[metric] = value
        return out
    hit = metric in unjudged or (kind == "unjudged_or_not_defined" and metric in undefined)
    if hit:
        out[metric] = value
        out["unjudged"] = [m for m in unjudged if m != metric]
        out["not_defined"] = [m for m in undefined if m != metric]
    return out


def missing_outcome_bounds(
    answer_records: Sequence[Mapping[str, Any]],
    *,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Return per dataset and variant the answer rows with the changed outcomes.

    Args:
        answer_records: Per-question answer score records, one per run.
        n_draws: FinanceBench sign-flip draws (100,000 registered).
    """
    docs = factorial35.documents(answer_records)
    every = factorial35._questions(answer_records)  # a question with no cell value counts too
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for variant, (metric, value, kind) in VARIANTS.items():
        records = [_changed(r, metric, value, kind) for r in answer_records]
        cells = factorial35.cell_means(records, metric)
        for dataset in sorted(cells):
            rows = []
            for number in ROWS[metric]:
                row = factorial35.ROWS[number - 1]
                d, excluded = factorial35.contrast(row, cells[dataset], every[dataset])
                test = (
                    factorial35._test(dataset, d, docs.get(dataset, {}), n_draws)
                    if d
                    else {"estimate": math.nan, "p_value": math.nan}
                )
                rows.append(
                    {"row": number, "metric": metric, "n": len(d), "excluded": excluded, **test}
                )
            out.setdefault(dataset, {})[variant] = rows
    return out
