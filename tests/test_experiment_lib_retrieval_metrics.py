"""Tests for the plain nDCG@10 and hit@page added to ``experiments/_lib/retrieval_metrics.py``.

Experiment 35 task 2.1. Known lists only: no store, no server. The last test
pins that the ported Experiment 22 definitions did not move.
"""

from __future__ import annotations

import math

import pytest
from experiments._lib.retrieval_metrics import (
    _metrics_for_query,
    hit_at_page,
    ndcg_at_k,
)

# ---------------------------------------------------------------- nDCG@10


def test_ndcg_is_one_for_a_perfect_ranking() -> None:
    assert ndcg_at_k(["a", "b", "x"], {"a", "b"}) == pytest.approx(1.0)


def test_ndcg_of_a_known_list_matches_the_hand_calculation() -> None:
    # Relevant a at rank 1, b at rank 3. DCG = 1/log2(2) + 1/log2(4) = 1.5.
    # Ideal puts both first: 1/log2(2) + 1/log2(3).
    expected = 1.5 / (1.0 + 1.0 / math.log2(3))
    assert ndcg_at_k(["a", "x", "b"], {"a", "b"}) == pytest.approx(expected)


def test_ndcg_is_zero_when_nothing_relevant_is_retrieved() -> None:
    assert ndcg_at_k(["x", "y"], {"a"}) == 0.0


def test_ndcg_is_zero_when_the_question_has_no_gold() -> None:
    assert ndcg_at_k(["a"], set()) == 0.0


def test_ndcg_ignores_ranks_beyond_k() -> None:
    ranking = [f"x{i}" for i in range(10)] + ["a"]
    assert ndcg_at_k(ranking, {"a"}, k=10) == 0.0
    assert ndcg_at_k(ranking, {"a"}, k=11) > 0.0


def test_ndcg_counts_a_repeated_relevant_id_once() -> None:
    assert ndcg_at_k(["a", "a", "a"], {"a"}) == pytest.approx(1.0)


# ---------------------------------------------------------------- hit@page


def test_merged_row_with_page_labels_hits_a_gold_page_inside_it() -> None:
    rows = [{"page_label": "5", "page_labels": ["5", "6"]}]
    assert hit_at_page(rows, {"6"}) is True


def test_page_label_is_the_fallback_when_page_labels_is_missing() -> None:
    assert hit_at_page([{"page_label": "6"}], {"6"}) is True
    assert hit_at_page([{"page_label": "6", "page_labels": None}], {"6"}) is True
    assert hit_at_page([{"page_label": "6", "page_labels": []}], {"6"}) is True


def test_page_labels_win_over_page_label_when_both_are_present() -> None:
    # The merged row's lowest page is 5; the gold page 6 is only in the list.
    assert hit_at_page([{"page_label": "5", "page_labels": ["5", "6"]}], {"5"}) is True
    assert hit_at_page([{"page_label": "6", "page_labels": ["4", "5"]}], {"6"}) is False


def test_hit_at_page_misses_when_no_row_holds_a_gold_page() -> None:
    assert hit_at_page([{"page_label": "4"}, {"page_labels": ["7", "8"]}], {"6"}) is False


def test_any_gold_page_counts_for_a_question_with_several_evidence_entries() -> None:
    assert hit_at_page([{"page_label": "9"}], {"3", "9"}) is True


def test_hit_at_page_accepts_integer_labels() -> None:
    assert hit_at_page([{"page_label": 6}], {"6"}) is True


def test_hit_at_page_only_reads_the_top_k_rows() -> None:
    rows = [{"page_label": str(p)} for p in range(1, 12)]
    assert hit_at_page(rows, {"11"}, k=10) is False
    assert hit_at_page(rows, {"11"}, k=11) is True


def test_a_row_without_any_page_never_hits() -> None:
    assert hit_at_page([{"page_label": None}, {}], {"6"}) is False


# ---------------------------------------------------------------- existing definitions


def test_existing_per_query_metrics_are_unchanged() -> None:
    metrics = _metrics_for_query(["p1", "p2", "p1"], {"relevant_parent_ids": ["p2"]})
    assert metrics["first_relevant_rank"] == 2
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["hit_at_5"] is True
    assert metrics["recall_at_1"] == 0.0
    assert metrics["recall_at_3"] == 1.0
