"""Experiment 35 differential-error rule and faithfulness-gate extras (A18; prereg 11.2, R10).

Rules under test: the GLM-5.3 sensitivity difference (2,048 minus 512) is
computed on the same resamples by question as the specificity difference
(seed 20261126); the rule fires when either 95% interval excludes zero; an
undefined sensitivity difference fails closed like the specificity one; the
gate reports prevalence, raw agreement and PABAK beside kappa.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests._exp35_fixtures import load

labels35 = load("labels35")
differential35 = load("differential35")

ROWS = [12, 13, 16, 17]


def _items(n_q: int = 10) -> list[dict[str, Any]]:
    return [
        {"item_id": f"{d}-{c}-{q}", "dataset": d, "qid": f"{c}-{q}", "chunk_size": c}
        for d in ("bioasq", "financebench", "freshstack")
        for c in (512, 1024, 2048)
        for q in range(n_q)
    ]


def _human(items: list[dict[str, Any]]) -> dict[str, str]:
    return {
        i["item_id"]: "supported" if int(i["qid"].split("-")[1]) % 2 else "not_supported"
        for i in items
    }


def _perfect(human: dict[str, str]) -> dict[str, str]:
    return {k: "supported" if v == "supported" else "unsupported" for k, v in human.items()}


def _gate(items, human, glm, clef=None) -> dict[str, Any]:
    clef = clef or _perfect(human)
    return labels35.faithfulness_gate(
        items, human, {"chat": glm, "clef_flash": clef}, n=300, decided_at="2026-11-27T10:00:00Z"
    )


# --- one set of resamples ---------------------------------------------------------------------


def test_paired_bootstrap_uses_one_set_of_resamples_for_every_statistic() -> None:
    items = [(f"q{i}", float(i)) for i in range(12)]

    def mean(rows: list[float]) -> float:
        return sum(rows) / len(rows)

    out = differential35.paired_bootstrap(
        items, {"a": mean, "b": lambda r: mean(r) + 100.0}, n=500, seed=20261126
    )
    # A constant shift keeps the bounds a fixed distance apart only when both
    # statistics are evaluated on the very same resamples.
    assert out["b"].lower - out["a"].lower == pytest.approx(100.0)
    assert out["b"].upper - out["a"].upper == pytest.approx(100.0)
    assert out["a"].n == 500 and out["a"].kept == 500


def test_paired_bootstrap_leaves_out_undefined_resamples_per_statistic() -> None:
    items = [(f"q{i}", i) for i in range(10)]
    out = differential35.paired_bootstrap(
        items, {"a": lambda r: float(len(r)), "b": lambda r: float("nan")}, n=100, seed=1
    )
    assert out["a"].testable and out["a"].undefined == 0
    assert out["b"].testable is False and out["b"].undefined == 100 and out["b"].kept == 0


# --- sensitivity difference in the gate -------------------------------------------------------


def test_sensitivity_difference_is_reported_with_the_same_seed_and_resamples() -> None:
    items = _items()
    human = _human(items)
    result = _gate(items, human, _perfect(human))
    diff = result["differential_error"]
    assert result["seeds"]["difference"] == 20261126
    assert diff["sensitivity_difference"]["estimate"] == pytest.approx(0.0)
    assert diff["sensitivity_difference"]["n"] == diff["difference"]["n"] == 300
    assert diff["excludes_zero"] is False and result["not_testable_rows"] == []


def test_rule_fires_when_only_the_sensitivity_interval_excludes_zero() -> None:
    items = _items()
    human = _human(items)
    glm = _perfect(human)
    for i in items:  # at 2,048 GLM-5.3 passes every human-unsupported claim
        if i["chunk_size"] == 2048 and human[i["item_id"]] != "supported":
            glm[i["item_id"]] = "supported"
    diff = _gate(items, human, glm)["differential_error"]
    assert diff["specificity_excludes_zero"] is False
    assert diff["sensitivity_excludes_zero"] is True
    assert diff["sensitivity_difference"]["estimate"] == pytest.approx(-1.0)
    assert diff["excludes_zero"] is True
    assert _gate(items, human, glm)["not_testable_rows"] == ROWS


def test_rule_still_fires_on_the_specificity_interval_alone() -> None:
    items = _items()
    human = _human(items)
    glm = _perfect(human)
    for i in items:  # at 2,048 GLM-5.3 rejects every human-supported claim
        if i["chunk_size"] == 2048 and human[i["item_id"]] == "supported":
            glm[i["item_id"]] = "unsupported"
    result = _gate(items, human, glm)
    diff = result["differential_error"]
    assert diff["specificity_excludes_zero"] is True
    assert diff["sensitivity_excludes_zero"] is False
    assert result["not_testable_rows"] == ROWS


def test_a_level_with_no_unsupported_claim_fails_closed() -> None:
    items = _items()
    human = {k: ("supported" if "-512-" in k else v) for k, v in _human(items).items()}
    result = _gate(items, human, _perfect(human))
    diff = result["differential_error"]
    assert diff["difference"]["testable"] is True  # specificity is defined
    assert diff["sensitivity_difference"]["testable"] is False
    assert result["not_testable_rows"] == ROWS


def test_over_5_percent_undefined_sensitivity_resamples_fail_closed() -> None:
    items = _items()
    human = _human(items)
    for i in items:  # only one question at 512 holds an unsupported claim
        if i["chunk_size"] == 512:
            human[i["item_id"]] = "not_supported" if i["item_id"] == "bioasq-512-0" else "supported"
    diff = _gate(items, human, _perfect(human))["differential_error"]["sensitivity_difference"]
    assert diff["undefined"] > 15 and diff["kept"] == 300 - diff["undefined"]
    assert diff["testable"] is False


# --- prevalence, raw agreement and PABAK ------------------------------------------------------


def test_gate_reports_prevalence_raw_agreement_and_pabak_beside_kappa() -> None:
    items = _items()
    human = _human(items)  # half the claims supported
    glm = _perfect(human)
    flipped = [i["item_id"] for i in items][:18]  # 18 of 90 verdicts disagree
    for k in flipped:
        glm[k] = "unsupported" if glm[k] == "supported" else "supported"
    chat = _gate(items, human, glm)["checkers"]["chat"]
    assert chat["prevalence"] == pytest.approx(0.5)
    assert chat["raw_agreement"] == pytest.approx(72 / 90)
    assert chat["pabak"] == pytest.approx(2 * 72 / 90 - 1)
    assert "kappa" in chat


def test_prevalence_counts_cant_tell_as_not_supported_and_left_out_figures_follow_kappa() -> None:
    items = _items()
    human = _human(items)
    glm = _perfect(human)
    first = items[0]["item_id"]
    human[first] = "cant_tell"
    glm[first] = "supported"
    chat = _gate(items, human, glm)["checkers"]["chat"]
    assert chat["raw_agreement"] == pytest.approx(89 / 90)
    left_out = chat["cant_tell_left_out_stats"]
    assert left_out["raw_agreement"] == pytest.approx(1.0)
    assert left_out["pabak"] == pytest.approx(1.0)


def test_specificity_difference_keeps_seed_20261126_and_the_registered_bounds() -> None:
    bootstrap35 = load("bootstrap35")
    items = _items()
    human = _human(items)
    glm = _perfect(human)
    for k in list(glm)[::7]:  # a few wrong verdicts so the interval has width
        glm[k] = "unsupported" if glm[k] == "supported" else "supported"
    rows = [
        (
            (i["dataset"], i["qid"]),
            (i["chunk_size"], human[i["item_id"]] == "supported", glm[i["item_id"]] == "supported"),
        )
        for i in items
    ]
    expected = bootstrap35.bootstrap_by_question(
        rows,
        lambda r: differential35.specificity_difference(list(r)),
        n=300,
        seed=20261126,
        fill=None,
    )
    got = _gate(items, human, glm)["differential_error"]["difference"]
    assert (got["lower"], got["upper"], got["undefined"]) == (
        expected.lower,
        expected.upper,
        expected.undefined,
    )


def test_paired_bootstrap_is_the_shared_bootstrap_with_undefined_left_out() -> None:
    bootstrap35 = load("bootstrap35")
    items = [(f"q{i % 7}", float(i)) for i in range(21)]
    stats = {"m": lambda r: sum(r) / len(r) if 0.0 in r else float("nan")}  # q0 not drawn
    got = differential35.paired_bootstrap(items, stats, n=300, seed=20261126)
    want = bootstrap35.bootstrap_many(items, stats, n=300, seed=20261126, fill=None)
    assert got["m"].as_dict() == want["m"].as_dict()  # as_dict: NaN never equals NaN
    assert 0 < got["m"].undefined < 300 and got["m"].kept == 300 - got["m"].undefined
