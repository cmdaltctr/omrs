"""Experiment 35 correctness gate per core dataset, ``correct35.py`` (task 14.6).

Rules under test (pre-registration section 11.2): seed 20261113 draws 50
half-B questions per dataset, each with the run-1 answer of a setup the seed
picks uniformly (150 and no Legal after drop step 1), with no Ragas score; the
page shows question, reference and answer; the Ragas score is cut at 0.5;
kappa is computed twice ("can't tell" as correct and as not correct) and both
must reach 0.60 with a lower bound of 0.40; the AUC lower bound must be above
0.5; undefined statistics fail closed; Legal has no gate; a failed gate marks
rows 14, 15, 18 and 19 not testable; nothing is pooled.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest
from tests import _exp35_mainrun_fixtures as fx
from tests._exp35_fixtures import load

correct35 = load("correct35")
bootstrap35 = load("bootstrap35")


def _draw(tmp_path: Path, *, drop: bool = False) -> list[dict]:
    out = tmp_path / "out"
    questions = fx.build(out)
    if drop:
        fx.drop_legal(out)
    return correct35.draw(out, tmp_path / "halves.json", questions, seed=20261113)


# --- sample ----------------------------------------------------------------------------------


def test_sample_is_200_answers_50_per_dataset_from_half_b(tmp_path: Path) -> None:
    items = _draw(tmp_path)
    assert len(items) == 200
    for dataset in fx.DATASETS:
        mine = [i for i in items if i["dataset"] == dataset]
        assert len(mine) == 50
        assert len({i["qid"] for i in mine}) == 50
        assert all(int(i["qid"][1:]) % 2 == 1 for i in mine)  # half B
    assert len({i["setup"] for i in items}) > 3  # the seed picks among setups
    assert all(
        i["answer"] == f"Claim one of {i['qid']} [1]. Claim two of {i['qid']} [1]." for i in items
    )


def test_same_seed_gives_the_same_answers_twice(tmp_path: Path) -> None:
    first = _draw(tmp_path / "a")
    second = _draw(tmp_path / "b")
    assert [(i["dataset"], i["qid"], i["setup"]) for i in first] == [
        (i["dataset"], i["qid"], i["setup"]) for i in second
    ]


def test_drop_step_1_draws_no_legal_answers(tmp_path: Path) -> None:
    items = _draw(tmp_path, drop=True)
    assert len(items) == 150
    assert "legal" not in {i["dataset"] for i in items}


def test_sample_holds_no_ragas_score(tmp_path: Path) -> None:
    text = json.dumps(_draw(tmp_path))
    assert "score" not in text and "ragas" not in text and "answer_correctness" not in text


def test_page_shows_question_reference_and_answer_only(tmp_path: Path) -> None:
    items = _draw(tmp_path)
    correct35.write_sample(tmp_path / "labels", items)
    page = correct35.write_page(tmp_path / "labels")
    text = page.read_text()
    data = json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))
    assert set(data["items"][0]) == {"item_id", "question", "reference", "answer"}
    assert [c[0] for c in data["choices"]] == ["correct", "not_correct", "cant_tell"]
    for banned in ("e4b-", "t20k", "c512", "score", "http"):
        assert banned not in text, banned


# --- statistics ------------------------------------------------------------------------------


def test_auc_hand_worked() -> None:
    assert correct35.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)
    assert correct35.auc([0.5, 0.5], [1, 0]) == pytest.approx(0.5)
    assert math.isnan(correct35.auc([0.2, 0.9], [1, 1]))


def _items(rows: list[tuple[str, float]], dataset: str = "bioasq") -> tuple[list, dict, dict]:
    items = [
        {"item_id": f"{dataset}{k}", "dataset": dataset, "qid": f"q{k}"} for k in range(len(rows))
    ]
    labels = {i["item_id"]: label for i, (label, _) in zip(items, rows, strict=True)}
    scores = {i["item_id"]: score for i, (_, score) in zip(items, rows, strict=True)}
    return items, labels, scores


# 8 correct at 0.9, 8 not correct at 0.1, 4 can't tell at 0.1.
TWENTY = [("correct", 0.9)] * 8 + [("not_correct", 0.1)] * 8 + [("cant_tell", 0.1)] * 4


def test_kappa_twice_with_prevalence_raw_agreement_and_pabak() -> None:
    items, labels, scores = _items(TWENTY)
    result = correct35.agree(items, labels, scores, n=500)["bioasq"]
    as_correct = result["cant_tell_correct"]
    # po 16/20 = 0.8; human 12/20 correct, Ragas 8/20; pe 0.48; kappa 0.32 / 0.52.
    assert as_correct["kappa"]["estimate"] == pytest.approx(0.32 / 0.52)
    assert (
        as_correct["prevalence"],
        as_correct["raw_agreement"],
        as_correct["pabak"],
    ) == pytest.approx((0.6, 0.8, 0.6))
    as_not = result["cant_tell_not_correct"]
    assert as_not["kappa"]["estimate"] == pytest.approx(1.0)
    assert (as_not["prevalence"], as_not["raw_agreement"], as_not["pabak"]) == pytest.approx(
        (0.4, 1.0, 1.0)
    )
    assert as_not["auc"]["estimate"] == pytest.approx(1.0)


def _boot(estimate: float, lower: float, testable: bool = True) -> object:
    return bootstrap35.BootResult(estimate, lower, 1.0, 10_000, 0, 10_000, testable)


@pytest.mark.parametrize(
    ("kappa_a", "kappa_b", "auc_lower", "passes"),
    [
        ((0.65, 0.45), (0.61, 0.40), 0.51, True),
        ((0.65, 0.45), (0.61, 0.39), 0.51, False),  # one computation below the lower bar
        ((0.59, 0.45), (0.61, 0.40), 0.51, False),  # point estimate below 0.60
        ((0.65, 0.45), (0.61, 0.40), 0.50, False),  # AUC lower bound must be above 0.5
    ],
)
def test_gate_rule(kappa_a: tuple, kappa_b: tuple, auc_lower: float, passes: bool) -> None:
    kappas = {"cant_tell_correct": _boot(*kappa_a), "cant_tell_not_correct": _boot(*kappa_b)}
    aucs = {
        "cant_tell_correct": _boot(0.8, auc_lower),
        "cant_tell_not_correct": _boot(0.8, auc_lower),
    }
    assert correct35.passes(kappas, aucs) is passes


def test_not_testable_kappa_fails_the_gate() -> None:
    kappas = {
        "cant_tell_correct": _boot(0.9, 0.8),
        "cant_tell_not_correct": _boot(0.9, 0.8, testable=False),
    }
    aucs = {k: _boot(0.9, 0.8) for k in kappas}
    assert correct35.passes(kappas, aucs) is False


def test_one_class_sample_fails_the_gate_and_marks_rows_not_testable() -> None:
    items, labels, scores = _items([("correct", 0.9)] * 20)
    result = correct35.agree(items, labels, scores, n=200)
    assert result["bioasq"]["pass"] is False
    assert result["not_testable_rows"] == {"bioasq": [14, 15, 18, 19]}


def test_over_5_percent_undefined_resamples_fails_the_gate() -> None:
    # One correct answer among 20: about 36% of resamples miss it, so kappa is undefined there.
    items, labels, scores = _items([("correct", 0.9)] + [("not_correct", 0.1)] * 19)
    result = correct35.agree(items, labels, scores, n=500)["bioasq"]["cant_tell_not_correct"]
    assert result["kappa"]["estimate"] == pytest.approx(1.0)
    assert result["kappa"]["undefined"] > 25
    assert result["kappa"]["testable"] is False


def test_legal_is_reported_with_no_gate_and_nothing_is_pooled() -> None:
    core = _items([("correct", 0.9)] * 10 + [("not_correct", 0.1)] * 10)
    legal = _items([("correct", 0.9)] * 20, dataset="legal")
    result = correct35.agree(
        core[0] + legal[0], {**core[1], **legal[1]}, {**core[2], **legal[2]}, n=200
    )
    assert result["legal"]["pass"] is None
    assert result["bioasq"]["pass"] is True
    assert result["not_testable_rows"] == {}
    assert "pooled" not in json.dumps(result)


def test_unscored_answer_is_left_out_and_counted() -> None:
    items, labels, scores = _items(TWENTY)
    scores[items[0]["item_id"]] = None
    result = correct35.agree(items, labels, scores, n=200)["bioasq"]
    assert result["unscored"] == 1
    assert result["cant_tell_not_correct"]["n"] == 19


def test_agree_cli_writes_the_gate_file_with_its_time(tmp_path: Path) -> None:
    items = _draw(tmp_path)
    label_dir = tmp_path / "labels"
    correct35.write_sample(label_dir, items)
    for who in ("L1", "L2"):
        (label_dir / f"labels-correctness-{who}.json").write_text(
            json.dumps(
                {
                    "set": "correctness",
                    "labeller": who,
                    "labels": {
                        i["item_id"]: "correct" if int(i["qid"][1:]) % 10 >= 5 else "not_correct"
                        for i in items
                    },
                }
            )
        )
    code = correct35.main(
        [
            "agree",
            "--out-dir",
            str(tmp_path / "out"),
            "--label-dir",
            str(label_dir),
            "--n",
            "200",
        ]
    )
    assert code == 0
    gate = json.loads((label_dir / "correctness-gate.json").read_text())
    assert gate["decided_at"]
    assert gate["result"]["bioasq"]["pass"] is True
    assert gate["result"]["legal"]["pass"] is None


def test_score_of_exactly_0_5_counts_as_correct() -> None:
    items, labels, scores = _items([("correct", 0.5)] * 10 + [("not_correct", 0.49)] * 10)
    result = correct35.agree(items, labels, scores, n=200)["bioasq"]
    assert result["cant_tell_not_correct"]["kappa"]["estimate"] == pytest.approx(1.0)


def test_undefined_kappa_resamples_take_0_and_count() -> None:
    # 3 correct among 45: about 4.5% of resamples hold no correct answer (kappa undefined).
    items, labels, scores = _items([("correct", 0.9)] * 3 + [("not_correct", 0.1)] * 42)
    kappa = correct35.agree(items, labels, scores, n=2_000)["bioasq"]["cant_tell_not_correct"][
        "kappa"
    ]
    assert 50 < kappa["undefined"] <= 100
    assert kappa["testable"] is True
    assert kappa["lower"] == 0.0  # the undefined resamples sit at 0, below index 50
