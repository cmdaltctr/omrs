"""Experiment 35 primary metrics from the retrieved rows (design D4).

Each search row becomes one unit ID, so the three datasets share the metric code:

* FinanceBench: ``<doc>#p<label>``. A row whose pages include a gold page of
  its document becomes that gold unit (a merged row spanning pages counts).
* FreshStack: the parent ID, through Experiment 22's chunk-to-parent join
  (``gold_rules.map_chunks_to_parents``).
* BioASQ: the passage ID, the stem of the source file name.

Metrics at K = 10, with the ``_lib`` functions: Recall@10 (share of gold units
in the top 10), MRR@10 (first gold rank), nDCG@10 (``ndcg_at_k``, binary
relevance, each unit counted once at its first rank) and, for FinanceBench,
hit@page (``hit_at_page`` on the rows of each gold document).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from experiments._lib.gold_rules import map_chunks_to_parents
from experiments._lib.retrieval_metrics import hit_at_page, ndcg_at_k

K = 10


def _stem(row: Mapping[str, Any]) -> str:
    meta = row.get("metadata") or {}
    return Path(str(meta.get("file_name") or row.get("source") or "")).stem


def _pages(row: Mapping[str, Any]) -> list[str]:
    labels = row.get("page_labels") or [row.get("page_label")]
    return [str(label) for label in labels if label is not None]


def ranked_units(
    dataset: str, question: Any, rows: Sequence[Mapping[str, Any]], id_map: Mapping[str, str]
) -> list[str]:
    """Return one unit ID per row of the top *K*, best first."""
    top = list(rows[:K])
    if dataset == "freshstack":
        return map_chunks_to_parents(top, id_map)
    if dataset == "bioasq":
        return [_stem(row) for row in top]
    units = []
    for row in top:
        doc, pages = _stem(row), _pages(row)
        gold = [p for p in pages if p in question.gold_pages.get(doc, ())]
        units.append(f"{doc}#p{(gold or pages or ['?'])[0]}")
    return units


def question_metrics(
    dataset: str, question: Any, rows: Sequence[Mapping[str, Any]], id_map: Mapping[str, str]
) -> dict[str, Any]:
    """Return the primary metrics of one question from its retrieved rows."""
    units = ranked_units(dataset, question, rows, id_map)
    gold = set(question.relevant)
    first = next((rank for rank, unit in enumerate(units, start=1) if unit in gold), None)
    metrics: dict[str, Any] = {
        "recall_at_10": len(gold & set(units)) / len(gold) if gold else 0.0,
        "mrr_at_10": 1.0 / first if first else 0.0,
        "ndcg_at_10": ndcg_at_k(units, gold, K),
    }
    if dataset == "financebench":
        top = list(rows[:K])
        metrics["hit_at_page"] = any(
            hit_at_page([r for r in top if _stem(r) == doc], pages, K)
            for doc, pages in question.gold_pages.items()
        )
    return metrics


def failed_metrics(dataset: str) -> dict[str, Any]:
    """Return the metrics of a question whose search failed: every score is zero."""
    metrics: dict[str, Any] = {"recall_at_10": 0.0, "mrr_at_10": 0.0, "ndcg_at_10": 0.0}
    if dataset == "financebench":
        metrics["hit_at_page"] = False
    return metrics


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the mean of each metric over every row; failed rows count as zero."""
    n = len(rows)
    summary: dict[str, Any] = {"n": n, "failed": sum(1 for r in rows if r.get("failed"))}
    names = sorted({name for r in rows for name in r["metrics"]})
    for name in names:
        values = [float(r["metrics"].get(name) or 0.0) for r in rows]
        summary[name] = sum(values) / n if n else None
    return summary
