"""Missing-outcome bounds of Experiment 35 (readiness task 16.20, A5 item 57; PR 12).

Registered sensitivity analyses on the answer rows: no-claim runs scored 1 and
scored 0, unjudged checker rows scored 0, and unjudged or not-defined Ragas
correctness runs scored 0. Every question of the variant enters the row.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests._exp35_fixtures import load

select35 = load("select35")
bounds35 = load("bounds35")

FAITH = "faithfulness_glm_factual"
CORRECT = "ragas_answer_correctness"
QIDS = ("q0", "q1", "q2", "q3")


def _setups() -> list[str]:
    crossed = [
        select35.Setup("4b", c, r, h).name
        for c in (512, 1024, 2048)
        for r in ("off", "4b")
        for h in ("off", "on")
    ]
    return crossed + [select35.Setup("4b", c, "4b", "on", True).name for c in (512, 1024, 2048)]


def _records() -> list[dict[str, Any]]:
    """Every value 0.5, one run, with four planted missing outcomes.

    q0: no factual claim in every crossed c1024 setup (rows 12 and 13).
    q1: Ragas correctness unjudged in e4b-c512-roff-hoff (row 14).
    q2: Ragas correctness not defined in e4b-c2048-roff-hoff (row 15).
    q3: checker row unjudged in e4b-c2048-roff-hoff (row 13).
    """
    rows = []
    for setup in _setups():
        grid = select35.parse_setup(setup)
        for qid in QIDS:
            row: dict[str, Any] = {
                "dataset": "freshstack",
                "setup": setup,
                "qid": qid,
                "run": 1,
                FAITH: 0.5,
                CORRECT: 0.5,
                "unjudged": [],
                "not_defined": [],
            }
            if qid == "q0" and grid.chunk == 1024 and not grid.t20k:
                row[FAITH] = None
            if qid == "q1" and setup == "e4b-c512-roff-hoff":
                row |= {CORRECT: None, "unjudged": [CORRECT]}
            if qid == "q2" and setup == "e4b-c2048-roff-hoff":
                row |= {CORRECT: None, "not_defined": [CORRECT]}
            if qid == "q3" and setup == "e4b-c2048-roff-hoff":
                row |= {FAITH: None, "unjudged": [FAITH]}
            rows.append(row)
    return rows


def _row(table: dict[str, Any], variant: str, number: int) -> dict[str, Any]:
    return {r["row"]: r for r in table["freshstack"][variant]}[number]


@pytest.fixture(scope="module")
def table() -> dict[str, Any]:
    return bounds35.missing_outcome_bounds(_records(), n_draws=200)


def test_variants_and_their_rows(table: dict[str, Any]) -> None:
    assert list(table["freshstack"]) == list(bounds35.VARIANTS)
    for variant, (metric, _, _) in bounds35.VARIANTS.items():
        rows = table["freshstack"][variant]
        want = [12, 13, 16, 17] if metric == FAITH else [14, 15, 18, 19]
        assert [r["row"] for r in rows] == want and all(r["metric"] == metric for r in rows)


def test_no_claim_runs_scored_1_and_0_bound_row_12(table: dict[str, Any]) -> None:
    high = _row(table, "no_claim_scored_1", 12)
    low = _row(table, "no_claim_scored_0", 12)
    assert high["n"] == 4 and low["n"] == 4  # q0 enters both
    assert high["estimate"] == pytest.approx(0.5 / 4)
    assert low["estimate"] == pytest.approx(-0.5 / 4)


def test_an_unjudged_checker_row_scored_0(table: dict[str, Any]) -> None:
    row = _row(table, "unjudged_scored_0", 13)
    assert row["n"] == 3  # q0 stays out: no claim is not unjudged
    assert row["estimate"] == pytest.approx(-(0.5 / 4) / 3)


def test_unjudged_and_not_defined_correctness_scored_0(table: dict[str, Any]) -> None:
    variant = "correctness_unjudged_or_not_defined_scored_0"
    assert _row(table, variant, 14)["n"] == 4
    assert _row(table, variant, 14)["estimate"] == pytest.approx((0.5 / 4) / 4)
    assert _row(table, variant, 15)["estimate"] == pytest.approx(-(0.5 / 4) / 4)


def test_the_records_are_not_changed() -> None:
    records = _records()
    bounds35.missing_outcome_bounds(records, n_draws=200)
    assert records == _records()


def test_a_question_with_no_cell_value_in_any_setup_is_counted_as_excluded() -> None:
    records = _records()
    for setup in _setups():
        records.append(
            {
                "dataset": "freshstack",
                "setup": setup,
                "qid": "q9",
                "run": 1,
                FAITH: None,
                CORRECT: None,
                "unjudged": [FAITH, CORRECT],
                "not_defined": [],
            }
        )
    out = bounds35.missing_outcome_bounds(records, n_draws=200)
    for variant, rows in out["freshstack"].items():
        for row in rows:
            assert row["n"] + row["excluded"] == len(QIDS) + 1, (variant, row["row"])
