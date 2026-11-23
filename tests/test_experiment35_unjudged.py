"""Unjudged-share audit trigger of Experiment 35 (readiness task 16.25; PR 11.3, 21).

The blind relevance audit runs only if the mean unjudged share in the top 10
units differs by more than 5 points: (a) hybrid on against off on FreshStack,
(b) OMRS against RAGFlow on a core dataset in Part 2; only where the qrels list
judged negatives.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests._exp35_fixtures import load

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
