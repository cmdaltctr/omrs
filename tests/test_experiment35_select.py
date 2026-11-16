"""Selection rule of Experiment 35 (readiness tasks 14.3 and 15.5, pre-registration 14.1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

select35 = load("select35")

CORE = ("financebench", "freshstack", "bioasq")
HALVES = {
    "financebench": {"f1": "A", "f2": "A", "f3": "B"},
    "freshstack": {"s1": "A", "s2": "A", "s3": "B"},
    "bioasq": {"b1": "A", "b2": "B"},
    "legal": {"l1": "A", "l2": "B"},
}
CHUNKS = {
    f"e{e}-c{c}": {"financebench": c // 8, "freshstack": c // 4, "bioasq": 10, "legal": 999}
    for e in ("0.6b", "4b", "8b")
    for c in (512, 1024, 2048)
}
DIMENSIONS = {"0.6b": 1024, "4b": 2560, "8b": 4096}


def _records(score: Callable[[Any, str, str], float]) -> list[dict[str, Any]]:
    """One record per setup, dataset and question; ``score(setup, dataset, half)``."""
    rows = []
    for name in select35.SEARCH_SETUPS:
        setup = select35.parse_setup(name)
        for dataset, questions in HALVES.items():
            for qid, half in questions.items():
                rows.append(
                    {
                        "dataset": dataset,
                        "setup": name,
                        "qid": qid,
                        "doc_id": "d",
                        "ndcg_at_10": score(setup, dataset, half),
                    }
                )
    return rows


def _select(records: list[dict[str, Any]]) -> dict[str, Any]:
    return select35.select(records, HALVES, CHUNKS, DIMENSIONS)


def test_seventy_two_setups() -> None:
    assert len(select35.SEARCH_SETUPS) == 72
    assert select35.parse_setup("e0.6b-c1024-r8b-hon").reranker == "8b"


def test_within_tolerance_on_unrounded_scores() -> None:
    assert 0.31 - 0.30 == 0.010000000000000009
    assert select35.within(0.31, 0.30)
    assert not select35.within(0.3100001, 0.30)


def test_gap_exactly_001_picks_smaller_embedder_and_0011_picks_best() -> None:
    base = {"0.6b": 0.30, "4b": 0.31, "8b": 0.20}
    chosen = _select(_records(lambda s, d, h: base[s.embedder]))
    assert chosen["embedder"] == "0.6b"
    base["4b"] = 0.311
    assert _select(_records(lambda s, d, h: base[s.embedder]))["embedder"] == "4b"
    base["4b"] = 0.3100001
    assert _select(_records(lambda s, d, h: base[s.embedder]))["embedder"] == "4b"


def test_equal_scores_pick_smaller_size() -> None:
    chosen = _select(_records(lambda s, d, h: 0.5))
    assert chosen["embedder"] == "0.6b"
    assert chosen["reranker"] == "0.6b"


def test_pooled_score_is_plain_mean_of_dataset_means() -> None:
    # FinanceBench has two half-A questions, BioASQ one. Question-weighted would differ.
    def score(s: Any, dataset: str, half: str) -> float:
        return {"financebench": 0.9, "freshstack": 0.3, "bioasq": 0.0}.get(dataset, 0.7)

    chosen = _select(_records(score))
    # Plain mean of 0.9, 0.3 and 0.0 is 0.4; question-weighted (2, 2, 1) would be 0.48.
    assert chosen["pooled_scores"]["e4b-c512-roff-hoff"] == pytest.approx(0.4)


def test_legal_scores_change_nothing() -> None:
    def plain(s: Any, dataset: str, half: str) -> float:
        return {"0.6b": 0.3, "4b": 0.5, "8b": 0.505}[s.embedder] + (s.chunk == 1024) * 0.1

    def legal_heavy(s: Any, dataset: str, half: str) -> float:
        bonus = 5.0 if dataset == "legal" and s.embedder == "8b" and s.reranker == "8b" else 0.0
        return plain(s, dataset, half) + bonus

    assert _select(_records(plain)) == _select(_records(legal_heavy))


def test_half_b_effect_changes_nothing() -> None:
    def plain(s: Any, dataset: str, half: str) -> float:
        return 0.4 + (s.embedder == "4b") * 0.05

    def half_b_heavy(s: Any, dataset: str, half: str) -> float:
        return plain(s, dataset, half) + (2.0 if half == "B" and s.embedder == "8b" else 0.0)

    assert _select(_records(plain)) == _select(_records(half_b_heavy))
    assert _select(_records(plain))["embedder"] == "4b"


def test_reranker_size_from_reranker_on_setups_at_chosen_embedder() -> None:
    def score(s: Any, dataset: str, half: str) -> float:
        value = {"0.6b": 0.2, "4b": 0.5, "8b": 0.3}[s.embedder]
        if s.embedder == "4b":
            value += {"off": 0.9, "0.6b": 0.0, "4b": 0.05, "8b": 0.02}[s.reranker]
        else:
            value += {"off": 0.0, "0.6b": 0.0, "4b": 0.0, "8b": 0.4}[s.reranker]
        return value

    chosen = _select(_records(score))
    assert chosen["embedder"] == "4b"
    assert chosen["reranker"] == "4b"  # off and other embedders do not take part
    assert set(chosen["reranker_scores"]) == {"0.6b", "4b", "8b"}


def test_cell_tie_order() -> None:
    # All 12 cells tie: reranker off, then hybrid off, then lowest index cost.
    # Index cost: FinanceBench c/8 + FreshStack c/4 + BioASQ 10 chunks; 512 is cheapest.
    chosen = _select(_records(lambda s, d, h: 0.5))
    assert chosen["cell"] == "e0.6b-c512-roff-hoff"

    # Only reranker-on cells tie at the top: hybrid off wins next.
    def on_only(s: Any, dataset: str, half: str) -> float:
        return 0.5 + (s.reranker != "off") * 0.1

    assert _select(_records(on_only))["cell"] == "e0.6b-c512-r0.6b-hoff"

    # Tied cells: reranker off with hybrid on, and reranker on with hybrid off.
    # Reranker off comes first in the order, so the first one wins.
    def crossed(s: Any, dataset: str, half: str) -> float:
        return 0.5 + ((s.reranker == "off") != (s.hybrid == "off")) * 0.1

    assert _select(_records(crossed))["cell"] == "e0.6b-c512-roff-hon"


def test_cell_lowest_index_cost_beats_smaller_chunk() -> None:
    chunks = {name: dict(counts) for name, counts in CHUNKS.items()}
    chunks["e0.6b-c512"]["freshstack"] = 10_000  # 512 now costs most
    chosen = select35.select(_records(lambda s, d, h: 0.5), HALVES, chunks, DIMENSIONS)
    assert chosen["cell"] == "e0.6b-c1024-roff-hoff"
    chunks["e0.6b-c1024"]["freshstack"] = chunks["e0.6b-c2048"]["freshstack"]
    chunks["e0.6b-c1024"]["financebench"] = chunks["e0.6b-c2048"]["financebench"]
    chosen = select35.select(_records(lambda s, d, h: 0.5), HALVES, chunks, DIMENSIONS)
    assert chosen["cell"] == "e0.6b-c1024-roff-hoff"  # equal cost: smaller chunk size


def test_cell_outside_tie_is_not_chosen() -> None:
    def score(s: Any, dataset: str, half: str) -> float:
        return 0.5 + (s.chunk == 2048 and s.hybrid == "on") * 0.0101

    assert _select(_records(score))["cell"] == "e0.6b-c2048-roff-hon"


def test_missing_setup_stops_and_names_it() -> None:
    records = [r for r in _records(lambda s, d, h: 0.5) if r["setup"] != "e8b-c2048-r4b-hon"]
    with pytest.raises(select35.SelectionError, match="e8b-c2048-r4b-hon"):
        _select(records)
    records = [
        r
        for r in _records(lambda s, d, h: 0.5)
        if not (r["setup"] == "e4b-c512-roff-hoff" and r["qid"] == "s2")
    ]
    with pytest.raises(select35.SelectionError, match="e4b-c512-roff-hoff.*freshstack"):
        _select(records)


def test_index_cost_is_chunks_times_dimension_over_core_datasets() -> None:
    costs = select35.index_costs(CHUNKS, DIMENSIONS)
    assert costs["e4b-c1024"] == (128 + 256 + 10) * 2560  # Legal's 999 chunks left out


def test_configuration_hash_known_answer() -> None:
    settings = {"b": 1, "a": "é", "nested": {"y": [1, 2], "x": None}}
    canonical = '{"a":"é","b":1,"halves_sha256":"00ff","nested":{"x":null,"y":[1,2]}}'
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert select35.configuration_hash(settings, "00ff") == expected
    assert select35.configuration_hash(settings, "00ff") == expected


def test_selection_json_lists_everything(tmp_path: Path) -> None:
    chosen = _select(_records(lambda s, d, h: 0.5))
    path = tmp_path / "selection.json"
    select35.write_selection(path, chosen, {"chunking": {"chunk_size": 512}}, "ab" * 32)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["pooled_scores"]) == 72
    assert set(saved["embedder_scores"]) == {"0.6b", "4b", "8b"}
    assert len(saved["cell_scores"]) == 12
    assert saved["embedder"] == "0.6b" and saved["reranker"] == "0.6b"
    assert saved["cell"] == "e0.6b-c512-roff-hoff"
    assert saved["halves_sha256"] == "ab" * 32
    assert saved["configuration_hash"] == select35.configuration_hash(
        {"chunking": {"chunk_size": 512}}, "ab" * 32
    )


def test_expected_maximum_hand_case() -> None:
    # Scores 0.1, 0.2, 0.3. n = 2: pairs give maxima 0.2, 0.3, 0.3, mean 0.8 / 3.
    curve = select35.expected_max_curve([0.3, 0.1, 0.2])
    assert curve == pytest.approx([0.2, 0.8 / 3, 0.3])
