"""Tests for ``experiments/_lib/determinism.py`` (Experiment 35, task 2.8).

The check compares the retrieved lists of repeated runs per question and
reports every mismatch with its size.
"""

from __future__ import annotations

import pytest
from experiments._lib.determinism import compare_runs


def _run() -> dict[str, list[str]]:
    return {
        "q1": ["a", "b", "c", "d"],
        "q2": ["e", "f", "g", "h"],
        "q3": ["i", "j", "k", "l"],
        "q4": ["m", "n", "o", "p"],
    }


def test_identical_runs_report_no_mismatch() -> None:
    report = compare_runs({1: _run(), 2: _run(), 3: _run()})
    assert report.ok
    assert report.questions_compared == 4
    assert report.n_differing == 0
    assert report.mismatches == []


def test_injected_difference_is_reported_with_its_size() -> None:
    run2 = _run()
    run3 = _run()
    run2["q2"][2] = "ZZ"  # q2 differs from run 1 at rank 3
    run3["q4"][0], run3["q4"][1] = run3["q4"][1], run3["q4"][0]  # q4 differs at rank 1
    run3["q2"][3] = "YY"  # q2 also differs in run 3, later than in run 2

    report = compare_runs({1: _run(), 2: run2, 3: run3})

    assert not report.ok
    assert report.n_differing == 2
    assert report.questions_compared == 4
    by_question = {m.question_id: m for m in report.mismatches}
    assert set(by_question) == {"q2", "q4"}
    assert by_question["q2"].first_differing_rank == 3
    assert by_question["q2"].differing_runs == (2, 3)
    assert by_question["q4"].first_differing_rank == 1
    assert by_question["q4"].differing_runs == (3,)


def test_mismatches_are_listed_in_question_order() -> None:
    run2 = _run()
    run2["q4"][0] = "ZZ"
    run2["q1"][0] = "ZZ"
    report = compare_runs({1: _run(), 2: run2})
    assert [m.question_id for m in report.mismatches] == ["q1", "q4"]


def test_a_shorter_list_differs_at_the_first_missing_rank() -> None:
    run2 = _run()
    run2["q3"] = ["i", "j"]
    report = compare_runs({1: _run(), 2: run2})
    assert report.n_differing == 1
    assert report.mismatches[0].question_id == "q3"
    assert report.mismatches[0].first_differing_rank == 3


def test_question_missing_from_a_run_is_a_mismatch() -> None:
    run3 = _run()
    del run3["q1"]
    report = compare_runs({1: _run(), 2: _run(), 3: run3})
    assert not report.ok
    assert report.n_differing == 1
    mismatch = report.mismatches[0]
    assert mismatch.question_id == "q1"
    assert mismatch.missing_in_runs == (3,)
    assert mismatch.first_differing_rank is None


def test_question_only_in_a_later_run_is_a_mismatch() -> None:
    run2 = _run()
    run2["q5"] = ["x"]
    report = compare_runs({1: _run(), 2: run2})
    assert report.questions_compared == 5
    assert [m.question_id for m in report.mismatches] == ["q5"]
    assert report.mismatches[0].missing_in_runs == (1,)


def test_report_serialises_to_plain_data() -> None:
    run2 = _run()
    run2["q1"][1] = "ZZ"
    data = compare_runs({1: _run(), 2: run2}).to_dict()
    assert data == {
        "ok": False,
        "questions_compared": 4,
        "questions_differing": 1,
        "mismatches": [
            {
                "question_id": "q1",
                "first_differing_rank": 2,
                "differing_runs": [2],
                "missing_in_runs": [],
            }
        ],
    }


def test_fewer_than_two_runs_is_an_error() -> None:
    with pytest.raises(ValueError, match="at least two runs"):
        compare_runs({1: _run()})
