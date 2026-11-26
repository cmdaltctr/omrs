"""Unjudged-share audit trigger of Experiment 35 (readiness task 16.25; PR 11.3, 21).

The blind relevance audit runs only if the mean unjudged share in the top 10
units differs by more than 5 points: (a) hybrid on against off on FreshStack,
(b) OMRS against RAGFlow on a core dataset in Part 2; only where the qrels list
judged negatives.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from tests._exp35_fixtures import load

datasets35 = load("datasets35")
select35 = load("select35")
unjudged35 = load("unjudged35")

#: Judged units per question: one gold unit and two judged negatives.
QRELS = {f"q{i}": {f"g{i}": 1, f"n{i}a": 0, f"n{i}b": 0} for i in range(2)}
POSITIVES_ONLY = {q: {u: r for u, r in per.items() if r > 0} for q, per in QRELS.items()}


def _units(qid: str, unjudged: int, size: int = 10) -> list[str]:
    """Return a top list with *unjudged* units outside the qrels; the rest are judged."""
    judged = list(QRELS[qid])
    head = [judged[i % len(judged)] for i in range(size - unjudged)]
    return head + [f"x{k}" for k in range(unjudged)]


def _records(counts: dict[str, list[int]], dataset: str = "freshstack") -> list[dict[str, Any]]:
    return [
        {"dataset": dataset, "setup": setup, "qid": f"q{i}", "units": _units(f"q{i}", n)}
        for setup, per in counts.items()
        for i, n in enumerate(per)
    ]


ON = [select35.Setup("4b", 512, "off", "on").name, select35.Setup("8b", 1024, "4b", "on").name]
OFF = [select35.Setup("4b", 512, "off", "off").name, select35.Setup("8b", 1024, "4b", "off").name]


def test_unjudged_share_counts_units_outside_the_qrels_over_10_ranks() -> None:
    assert unjudged35.unjudged_share(_units("q0", 3), QRELS["q0"]) == pytest.approx(0.3)
    assert unjudged35.unjudged_share(["g0", "x1"], QRELS["q0"]) == pytest.approx(0.1)
    placeholder = ["unmapped:c9", *_units("q0", 0, 9)]
    assert unjudged35.unjudged_share(placeholder, QRELS["q0"]) == pytest.approx(0.1)


def test_hybrid_trigger_fires_on_a_gap_above_5_points() -> None:
    records = _records({ON[0]: [6, 6], ON[1]: [6, 6], OFF[0]: [5, 5], OFF[1]: [5, 5]})
    trigger = unjudged35.hybrid_trigger(records, QRELS)
    assert trigger["defined"] is True
    assert trigger["hybrid_on"] == pytest.approx(0.6)
    assert trigger["hybrid_off"] == pytest.approx(0.5)
    assert trigger["gap"] == pytest.approx(0.1)
    assert trigger["fires"] is True


def test_a_gap_of_exactly_5_points_does_not_fire() -> None:
    # On: 5 and 6 unjudged units (0.55); off: 5 and 5 (0.5). In floats 0.55 - 0.5 > 0.05.
    records = _records({ON[0]: [5, 6], OFF[0]: [5, 5]})
    trigger = unjudged35.hybrid_trigger(records, QRELS)
    assert trigger["gap"] == pytest.approx(0.05)
    assert trigger["fires"] is False


def test_the_gap_is_absolute_and_blind_to_the_side() -> None:
    records = _records({ON[0]: [2, 2], OFF[0]: [5, 5]})
    trigger = unjudged35.hybrid_trigger(records, QRELS)
    assert trigger["gap"] == pytest.approx(0.3) and trigger["fires"] is True


def test_hybrid_trigger_reads_freshstack_only() -> None:
    records = _records({ON[0]: [9, 9], OFF[0]: [0, 0]}, dataset="bioasq")
    records += _records({ON[0]: [5, 5], OFF[0]: [5, 5]})
    assert unjudged35.hybrid_trigger(records, QRELS)["fires"] is False


def test_positives_only_qrels_leave_the_trigger_undefined() -> None:
    records = _records({ON[0]: [9, 9], OFF[0]: [0, 0]})
    trigger = unjudged35.hybrid_trigger(records, POSITIVES_ONLY)
    assert trigger == {
        "dataset": "freshstack",
        "defined": False,
        "hybrid_on": None,
        "hybrid_off": None,
        "gap": None,
        "fires": False,
        "note": unjudged35.NOT_DEFINED,
    }


def test_system_trigger_per_core_dataset() -> None:
    omrs = _records({"selected": [3, 3]}, "bioasq") + _records({"selected": [3, 3]}, "freshstack")
    flow = _records({"ragflow": [9, 9]}, "bioasq") + _records({"ragflow": [3, 4]}, "freshstack")
    qrels = {"bioasq": QRELS, "freshstack": QRELS, "financebench": POSITIVES_ONLY}
    trigger = unjudged35.system_trigger(omrs, flow, qrels)
    assert trigger["bioasq"]["fires"] is True and trigger["bioasq"]["gap"] == pytest.approx(0.6)
    assert trigger["freshstack"]["fires"] is False
    assert trigger["financebench"]["defined"] is False
    assert trigger["fires"] is True


def test_share_table_gives_the_mean_per_setup_and_dataset() -> None:
    table = unjudged35.share_table(_records({ON[0]: [2, 4], OFF[0]: [0, 0]}), {"freshstack": QRELS})
    assert table["freshstack"][ON[0]] == pytest.approx(0.3)
    assert table["freshstack"][OFF[0]] == pytest.approx(0.0)


# --- condensed-list nDCG@10 (Sakai 2007; PR 21, RDY 16.4) -----------------------------------

#: Two relevant units (A, B) and two judged non-relevant units (N1, N2).
JUDGED = {"A": 1, "B": 1, "N1": 0, "N2": 0}


def test_condensed_ndcg_removes_unjudged_units_before_the_cut_known_answer() -> None:
    # Condensed list [A, N1, B]: DCG = 1/log2(2) + 1/log2(4) = 1.5;
    # ideal for 2 relevant = 1 + 1/log2(3) = 1.6309298; condensed = 0.9197208.
    ranked = ["X1", "A", "N1", "X2", "B", "X3"]
    assert unjudged35.condensed_ndcg(ranked, JUDGED) == pytest.approx(0.9197208, abs=1e-7)
    # The plain score keeps the unjudged units in place: A at 2, B at 5.
    plain = load("scoring35").ndcg_at_k(ranked, {"A", "B"}, 10)
    assert plain == pytest.approx(0.6240505, abs=1e-7)


def test_condensed_ndcg_reads_a_relevant_unit_from_past_rank_10() -> None:
    ranked = [f"X{i}" for i in range(10)] + ["A"]
    assert load("scoring35").ndcg_at_k(ranked, {"A", "B"}, 10) == 0.0
    assert unjudged35.condensed_ndcg(ranked, JUDGED) == pytest.approx(1 / 1.6309298, abs=1e-7)


def _fs_search() -> list[dict[str, Any]]:
    """FreshStack records: 0.6B ranks a judged negative above A; 4B and 8B rank A first.

    Unjudged units lead every list, so only the condensed list sees the gap.
    """
    rows = []
    for name in select35.SEARCH_SETUPS:
        lead = ["N2", "A"] if select35.parse_setup(name).embedder == "0.6b" else ["A", "N2"]
        for i in range(6):
            ranked = [*(f"X{k}" for k in range(10)), *lead, "N1", "B"]
            plain = load("scoring35").ndcg_at_k(ranked, {"A", "B"}, 10)
            row = {"dataset": "freshstack", "setup": name, "qid": f"q{i}", "ndcg_at_10": plain}
            rows.append({**row, "units": ranked[:10], "ranked_units": ranked})
    return rows


def test_condensed_rows_h1_to_h5_on_a_dataset_with_judged_negatives() -> None:
    qrels = {"freshstack": {f"q{i}": JUDGED for i in range(6)}}
    table = unjudged35.condensed_rows(_fs_search(), qrels)
    rows = {r["row"]: r for r in table["freshstack"]["rows"]}
    assert table["freshstack"]["defined"] is True
    assert sorted(rows) == list(range(1, 9))  # rows 1 to 8 are H1 to H5
    assert {r["hypothesis"] for r in rows.values()} == {"H1", "H2", "H3", "H4", "H5"}
    # Condensed: 0.6B [N2, A, N1, B] against 4B [A, N2, N1, B]; A moves from rank 2 to 1.
    gain = (1 + 1 / np.log2(5)) / (1 + 1 / np.log2(3)) - (1 / np.log2(3) + 1 / np.log2(5)) / (
        1 + 1 / np.log2(3)
    )
    assert rows[1]["estimate"] == pytest.approx(gain)
    assert rows[1]["plain_estimate"] == pytest.approx(0.0)  # A sits past rank 10 for both
    assert rows[2]["estimate"] == pytest.approx(0.0)  # 8B against 4B: the same lists
    assert rows[1]["n"] == 6 and rows[1]["metric"] == unjudged35.CONDENSED


def test_positives_only_qrels_state_that_neither_can_be_computed() -> None:
    qrels = {"freshstack": {f"q{i}": JUDGED for i in range(6)},
             "bioasq": POSITIVES_ONLY}  # fmt: skip
    records = _fs_search()
    report = unjudged35.report(records, qrels)
    assert report["bioasq"] == {"defined": False, "note": unjudged35.NEITHER}
    assert report["freshstack"]["defined"] is True
    assert set(report["freshstack"]) == {"defined", "unjudged_share", "condensed_ndcg_rows"}
    assert len(report["freshstack"]["condensed_ndcg_rows"]) == 8


def test_freshstack_qrels_grade_nugget_negatives_0_and_relevant_units_1(tmp_path) -> None:
    import json

    gt = tmp_path / "experiments" / "22-raw-query-qwen4b-baseline-2026-09-07" / "ground-truth.json"
    gt.parent.mkdir(parents=True)
    nuggets = [
        {"relevant_corpus_ids": ["a"], "non_relevant_corpus_ids": ["b", "n"]},
        {"relevant_corpus_ids": ["b"], "non_relevant_corpus_ids": ["n", "m"]},
    ]
    query = {"query_id": "1", "query_title": "t", "query_text": "x",
             "relevant_parent_ids": ["a", "b"], "nuggets": nuggets}  # fmt: skip
    gt.write_text(json.dumps({"queries": [query]}), encoding="utf-8")
    # "b" is non-relevant to one nugget but relevant to the query: it stays relevant.
    assert datasets35.qrels("freshstack", tmp_path) == {"1": {"a": 1, "b": 1, "n": 0, "m": 0}}
