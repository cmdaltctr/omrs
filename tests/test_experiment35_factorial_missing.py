"""Factorial analysis of Experiment 35: missing outcomes, drops and the guard.

Review R3-02, R3-03, R3-04, R3-05, R3-10, R3-11 and R3-12; pre-registration
sections 7 (H8b claim), 12 (missing outcomes), 14.2 (half-B guard) and 17
(drop step 1). The record builders come from ``test_experiment35_factorial``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests import test_experiment35_factorial as base
from tests._exp35_fixtures import load, open_half_b

factorial35 = load("factorial35")
scoring35 = load("scoring35")

FAITH, CORRECT = "faithfulness_glm_factual", "ragas_answer_correctness"
CELL = "e4b-c512-roff-hoff"


def _rows(result: dict[str, Any], dataset: str) -> dict[int, dict[str, Any]]:
    return {r["row"]: r for r in result["datasets"][dataset]}


def _mark(answers: list[dict], dataset: str, qid: str, *, setup: str | None = None, **change):
    for row in answers:
        if row["dataset"] == dataset and row["qid"] == qid and setup in (None, row["setup"]):
            if change.get("run") in (None, row["run"]):
                row.update({k: v for k, v in change.items() if k != "run"})


def test_an_unjudged_run_drops_the_cell_and_is_counted() -> None:
    # Counter-example of R3-03: run 2 of one crossed cell of q00 is unjudged.
    answers = base._answers()
    _mark(answers, "freshstack", "q00", setup=CELL, run=2, **{FAITH: None, "unjudged": [FAITH]})
    result = factorial35.analyse(base._search(), answers, **base.FAST)
    row12 = _rows(result, "freshstack")[12]
    assert row12["n"] == base.SIZES["freshstack"] - 1
    assert row12["excluded"] == 1 and row12["excluded_unjudged"] == 1
    assert row12["excluded_no_value"] == 0
    assert _rows(result, "freshstack")[14]["excluded"] == 0  # correctness was judged


def test_a_no_claim_run_is_left_out_of_the_run_mean_only() -> None:
    answers = base._answers()
    _mark(answers, "freshstack", "q00", setup=CELL, run=2, **{FAITH: None})
    row12 = _rows(factorial35.analyse(base._search(), answers, **base.FAST), "freshstack")[12]
    assert row12["n"] == base.SIZES["freshstack"] and row12["excluded"] == 0


def test_an_undefined_correctness_run_is_left_out_of_the_run_mean_and_counted() -> None:
    # A Ragas NaN (not_defined) is no value, as a no-claim run: the other runs stand.
    answers = base._answers()
    _mark(
        answers, "freshstack", "q00", setup=CELL, run=2, **{CORRECT: None, "not_defined": [CORRECT]}
    )
    row14 = _rows(factorial35.analyse(base._search(), answers, **base.FAST), "freshstack")[14]
    assert row14["n"] == base.SIZES["freshstack"] and row14["excluded"] == 0
    # Every run of the cell undefined: the question leaves the row, counted in its own column.
    _mark(answers, "freshstack", "q00", setup=CELL, **{CORRECT: None, "not_defined": [CORRECT]})
    row14 = _rows(factorial35.analyse(base._search(), answers, **base.FAST), "freshstack")[14]
    assert row14["excluded"] == 1 and row14["excluded_not_defined"] == 1
    assert row14["excluded_no_value"] == 0 and row14["excluded_unjudged"] == 0


def test_a_question_with_no_value_in_any_cell_is_counted() -> None:
    # Counter-example of R3-04: every answer of q05 has no factual claim.
    answers = base._answers()
    _mark(answers, "freshstack", "q05", **{FAITH: None})
    row12 = _rows(factorial35.analyse(base._search(), answers, **base.FAST), "freshstack")[12]
    assert row12["n"] == base.SIZES["freshstack"] - 1
    assert row12["excluded"] == 1 and row12["excluded_no_value"] == 1


def test_a_closed_missing_answer_row_keeps_its_question_document() -> None:
    # Counter-example of R3-05: the last answer record of q00 has no doc_id.
    answers = base._answers()
    _mark(answers, "financebench", "q00", run=3, doc_id=None)
    _mark(answers, "financebench", "q03", run=3, doc_id=None)
    result = factorial35.analyse(base._search(), answers, **base.FAST)
    planted = factorial35.analyse(base._search(), base._answers(), **base.FAST)
    assert _rows(result, "financebench")[1] == _rows(planted, "financebench")[1]


def test_h8b_sensitivity_survives_a_missing_t20k_answer() -> None:
    # Counter-example of R3-10: a closed-missing -t20k answer row has no cut total.
    answers = base._answers()
    t20k = "e4b-c512-r4b-hon-t20k"
    _mark(answers, "freshstack", "q00", setup=t20k, run=3, cut_tokens=None)
    kept = factorial35.h8b_questions(answers)
    assert "q00" in kept["freshstack"]  # runs 2 and 3 give the cut total
    _mark(answers, "freshstack", "q01", setup=t20k, cut_tokens=None)
    kept = factorial35.h8b_questions(answers)
    assert "q01" not in kept["freshstack"]  # no run gives it: left out
    result = factorial35.analyse(base._search(), answers, **base.FAST)
    fs = result["h8b_sensitivity"]["freshstack"]
    assert fs["questions_kept"] == base.SIZES["freshstack"] - 1
    assert fs["no_cut_total"] == 1


def test_analysis_runs_after_drop_step_one() -> None:
    # Counter-example of R3-11: Legal search records, no Legal answers.
    answers = [r for r in base._answers() if r["dataset"] != "legal"]
    with pytest.raises(ValueError, match="legal"):  # no drop recorded: incomplete
        factorial35.analyse(base._search(), answers, **base.FAST)
    result = factorial35.analyse(base._search(), answers, dropped=("legal",), **base.FAST)
    legal = _rows(result, "legal")
    assert legal[1]["exploratory"] and legal[1]["n"] == base.SIZES["legal"]
    assert all(legal[r]["dropped"] for r in range(12, 20))
    assert not any(legal[r].get("dropped") for r in range(1, 12))
    assert (
        result["hypotheses"]
        == factorial35.analyse(base._search(), base._answers(), **base.FAST)["hypotheses"]
    )  # Legal has no family


def _claims(h8b_sign: int, sensitivity_sign: int) -> dict[str, str | None]:
    held = {"holds": True, "rows": [16], "sign": h8b_sign}
    hypotheses = {
        "H8a": {"faithfulness": {"holds": False}, "correctness": {"holds": False}},
        "H8b": {"faithfulness": held, "correctness": {**held, "holds": False}},
    }
    sensitivity = {"sign": {16: sensitivity_sign, 17: 0, 18: 0, 19: 0}}
    return factorial35._claims(hypotheses, sensitivity)


def test_h8b_claim_uses_the_registered_wording() -> None:
    # Protocol 0.14 item 26: "chunk size itself changes X" is withdrawn.
    claims = _claims(1, 1)
    assert claims["faithfulness"] == (
        "chunk size changes faithfulness at a fixed pre-assembly evidence budget"
    )
    assert claims["correctness"] is None
    assert _claims(1, -1)["faithfulness"] is None


def test_confirmatory_result_refuses_while_half_b_is_locked(tmp_path: Path) -> None:
    (tmp_path / "faithfulness-gate.json").write_text(json.dumps({"not_testable_rows": []}))
    gate = {"result": {"not_testable_rows": {}}}
    (tmp_path / "correctness-gate.json").write_text(json.dumps(gate))
    out = tmp_path / "factorial.json"
    with pytest.raises(scoring35.HalfBLocked):
        factorial35.write_confirmatory(out, [], [], label_dir=tmp_path, root=tmp_path, **base.FAST)
    assert not out.exists()
    open_half_b(tmp_path)
    (tmp_path / "join.json").write_text(json.dumps({"ok": True}))
    # The drop record of the output folder reaches the analysis (drop step 1).
    (tmp_path / "drops.json").write_text(json.dumps({"drops": [{"step": 1}]}))
    answers = [r for r in base._answers() if r["dataset"] != "legal"]
    result = factorial35.write_confirmatory(
        out, base._search(), answers, label_dir=tmp_path, root=tmp_path, **base.FAST
    )
    assert out.exists() and _rows(result, "legal")[12]["dropped"]
