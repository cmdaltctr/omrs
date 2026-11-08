"""Tests for the ranking keys and the Part C neighbour comparison (review fixes, 2026-11-08).

Run with: uv run --no-sync pytest test_ranking_lib.py -q
"""

from __future__ import annotations

import pytest
from ranking_lib import EmptyResultIdError, neighbour_mismatches, result_id


def test_result_id_prefers_chunk_id():
    assert result_id({"chunk_id": "c1", "id": "x"}) == "c1"


def test_result_id_falls_back_to_id():
    assert result_id({"id": "x"}) == "x"


@pytest.mark.parametrize("item", [{}, {"chunk_id": ""}, {"id": ""}, {"chunk_id": None}])
def test_result_id_refuses_a_blank_id(item):
    with pytest.raises(EmptyResultIdError, match="chunk_id"):
        result_id(item)


def _unit(*xs: float) -> list[float]:
    norm = sum(x * x for x in xs) ** 0.5
    return [x / norm for x in xs]


VECTORS = {
    "a": _unit(1, 0, 0),
    "b": _unit(0.9, 0.1, 0),
    "c": _unit(0.3, 1, 0),
    "d": _unit(0.2, 0.9, 0.1),
}


def test_identical_vectors_give_no_neighbour_change():
    assert neighbour_mismatches(VECTORS, dict(VECTORS), k=2) == []


def test_a_moved_vector_names_the_query_and_both_lists():
    moved = dict(VECTORS)
    moved["b"] = _unit(0, 0.95, 0.05)  # b now sits next to c and d, not a
    found = neighbour_mismatches(VECTORS, moved, k=1)  # a: b under exact, c under fast
    queries = {m["query"] for m in found}
    assert "a" in queries
    row = next(m for m in found if m["query"] == "a")
    assert row["exact"] != row["fast"]


def test_different_id_sets_are_refused():
    with pytest.raises(ValueError, match="same chunk ids"):
        neighbour_mismatches(VECTORS, {"a": VECTORS["a"]}, k=2)
