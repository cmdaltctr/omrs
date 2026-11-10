"""Gold-label rules for the Experiment 35 datasets.

One small function per dataset rule, so every arm scores hits the same way:

* FinanceBench: convert the dataset's zero-indexed page to the label OMRS stores.
* FreshStack: map retrieved chunks to parent documents. Ported from Experiment
  22's ``run_eval.py`` (its folder name starts with a digit, so it cannot be
  imported). The first rank of each parent is kept by ``parent_first_ranks``.
* BioASQ: a gold passage ID in the top K is a hit.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from experiments._lib.retrieval_metrics import _rank_map

TOP_K = 10


def financebench_page_label(evidence_page_num: int) -> str:
    """Convert a FinanceBench ``evidence_page_num`` to an OMRS ``page_label``.

    The dataset counts pages from 0. The PDF readers store 1-based labels
    (``str(page)``), so dataset page 59 is label ``"60"``.

    Args:
        evidence_page_num: Zero-indexed page from the dataset.

    Returns:
        The label as OMRS stores it, for example ``"60"``.

    Raises:
        ValueError: If the page number is negative.
    """
    if evidence_page_num < 0:
        raise ValueError(f"evidence_page_num must be 0 or more, got {evidence_page_num}")
    return str(evidence_page_num + 1)


def map_chunks_to_parents(
    rows: Sequence[Mapping[str, Any]], id_map: Mapping[str, str]
) -> list[str]:
    """Map retrieved chunks to FreshStack parent IDs, in rank order.

    Same join as Experiment 22: chunk ``file_name`` metadata (else the base
    name of ``source``) looks up the parent ID. A chunk with no parent is
    dropped. The list keeps repeats, so three chunks of one parent give three
    entries. ``parent_first_ranks`` (and the metric code) count each parent once.

    Args:
        rows: Retrieved chunk rows, best first.
        id_map: File name to parent ID.
    """
    parent_ids: list[str] = []
    for row in rows:
        meta = row.get("metadata") or {}
        name = str(meta.get("file_name") or Path(str(row.get("source") or "")).name)
        parent_id = id_map.get(name)
        if parent_id:
            parent_ids.append(parent_id)
    return parent_ids


def parent_first_ranks(parent_ids: Sequence[str]) -> dict[str, int]:
    """Rank of each parent's first chunk, 1-based, from a raw parent list."""
    return _rank_map(list(parent_ids))


def bioasq_passage_hit(
    ranked_passage_ids: Sequence[object], gold_passage_ids: Collection[object], k: int = TOP_K
) -> bool:
    """True when a gold passage ID is in the top ``k`` retrieved passages.

    IDs compare as text, so ``123`` and ``"123"`` match.

    Args:
        ranked_passage_ids: Passage ID of each retrieved chunk, best first.
        gold_passage_ids: The question's ``relevant_passage_ids``.
        k: Cut-off rank.
    """
    gold = {str(passage_id) for passage_id in gold_passage_ids}
    return any(str(passage_id) in gold for passage_id in ranked_passage_ids[:k])
