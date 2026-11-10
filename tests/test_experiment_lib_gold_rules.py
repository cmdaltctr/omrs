"""Tests for ``experiments/_lib/gold_rules.py`` (Experiment 35 tasks 2.2 to 2.4).

Known values only: no store, no server, no dataset files.
"""

from __future__ import annotations

import pytest
from experiments._lib.gold_rules import (
    bioasq_passage_hit,
    financebench_page_label,
    map_chunks_to_parents,
    parent_first_ranks,
)
from experiments._lib.retrieval_metrics import _metrics_for_query, ndcg_at_k

# ---------------------------------------------------------------- 2.2 FinanceBench page


def test_zero_indexed_gold_page_becomes_the_one_based_omrs_label() -> None:
    # Dataset page 59 is the 60th page of the PDF; OMRS stores "60".
    assert financebench_page_label(59) == "60"


def test_first_dataset_page_is_omrs_page_one() -> None:
    assert financebench_page_label(0) == "1"


def test_negative_dataset_page_is_rejected() -> None:
    with pytest.raises(ValueError, match="evidence_page_num"):
        financebench_page_label(-1)


# ---------------------------------------------------------------- 2.3 FreshStack parents

ID_MAP = {"a-1.md": "P1", "a-2.md": "P1", "a-3.md": "P1", "b-1.md": "P2", "c-1.md": "P3"}


def _row(name: str) -> dict:
    return {"metadata": {"file_name": name}}


def test_chunks_map_to_their_parent_ids_in_rank_order() -> None:
    rows = [_row("b-1.md"), _row("a-1.md"), _row("c-1.md")]
    assert map_chunks_to_parents(rows, ID_MAP) == ["P2", "P1", "P3"]


def test_source_path_is_the_fallback_when_file_name_is_missing() -> None:
    rows = [{"source": "/corpus/dir/c-1.md", "metadata": {}}]
    assert map_chunks_to_parents(rows, ID_MAP) == ["P3"]


def test_chunk_with_an_unknown_file_is_dropped() -> None:
    assert map_chunks_to_parents([_row("zzz.md"), _row("b-1.md")], ID_MAP) == ["P2"]


def test_three_chunks_of_one_parent_count_once_at_the_first_rank() -> None:
    rows = [_row("b-1.md"), _row("a-1.md"), _row("a-2.md"), _row("a-3.md"), _row("c-1.md")]
    parents = map_chunks_to_parents(rows, ID_MAP)
    assert parent_first_ranks(parents) == {"P2": 1, "P1": 2, "P3": 5}
    metrics = _metrics_for_query(parents, {"relevant_parent_ids": ["P1", "P3"]})
    assert metrics["first_relevant_rank"] == 2
    assert metrics["recall_at_10"] == 1.0  # two gold parents found, P1 counted once
    assert metrics["recall_at_3"] == 0.5  # P3 sits at rank 5, P1 is not double-counted


def test_repeated_parent_does_not_inflate_ndcg() -> None:
    parents = map_chunks_to_parents([_row("a-1.md"), _row("a-2.md"), _row("a-3.md")], ID_MAP)
    assert ndcg_at_k(parents, {"P1"}) == pytest.approx(1.0)


# ---------------------------------------------------------------- 2.4 BioASQ passage


def test_gold_passage_in_the_top_ten_is_a_hit() -> None:
    ranked = [f"x{i}" for i in range(9)] + ["g1"]
    assert bioasq_passage_hit(ranked, {"g1", "g2"}) is True


def test_gold_passage_at_rank_eleven_is_a_miss() -> None:
    ranked = [f"x{i}" for i in range(10)] + ["g1"]
    assert bioasq_passage_hit(ranked, {"g1"}) is False


def test_no_gold_passage_retrieved_is_a_miss() -> None:
    assert bioasq_passage_hit(["x", "y"], {"g1"}) is False


def test_passage_ids_compare_as_text() -> None:
    assert bioasq_passage_hit([123], {"123"}) is True
