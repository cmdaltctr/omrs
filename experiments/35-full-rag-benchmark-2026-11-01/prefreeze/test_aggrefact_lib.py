"""Tests of the LLM-AggreFact scoring rules (hand-computed tiny sets)."""

from __future__ import annotations

import aggrefact_lib as lib
import pytest


def _row(idx, dataset, label, verdict, error=None):
    return {"idx": idx, "dataset": dataset, "label": label, "verdict": verdict, "error": error}


def _set(dataset, start, tp, fn, tn, fp):
    """Return rows with the given confusion counts."""
    rows, idx = [], start
    for label, verdict, n in (
        (1, "supported", tp), (1, "unsupported", fn), (0, "unsupported", tn), (0, "supported", fp),
    ):  # fmt: skip
        for _ in range(n):
            rows.append(_row(idx, dataset, label, verdict))
            idx += 1
    return rows


def test_verdict_names_match_omrs():
    from omrs.core.answer import verify

    assert lib.SUPPORTED == verify.VERDICT_SUPPORTED
    assert lib.UNPARSEABLE == verify.VERDICT_UNPARSEABLE


def test_published_values_in_one_dict():
    assert lib.PUBLISHED == {
        "clef_flash": {"average": 76.6, "RAGTruth": 83.2},
        "granite_guardian": {"average": 76.5, "RAGTruth": 82.2},
    }


def test_predicted_supported():
    assert lib.predicted_supported("supported")
    assert not lib.predicted_supported("unsupported")
    assert not lib.predicted_supported("unparseable")
    assert not lib.predicted_supported(None)


def test_balanced_accuracy_hand_computed():
    # TPR 3/4 = 0.75, TNR 2/4 = 0.5: (0.75 + 0.5) / 2 = 62.5 points.
    # Unbalanced on purpose: TPR 3/4, TNR 1/2 gives 62.5; plain accuracy would give 4/6.
    board = lib.leaderboard(_set("A", 0, tp=3, fn=1, tn=1, fp=1))
    assert board["datasets"]["A"]["balanced_accuracy"] == pytest.approx(62.5)
    assert board["datasets"]["A"]["rows"] == 6


def test_leaderboard_is_plain_mean_over_datasets():
    # A: 62.5. RAGTruth: TPR 1/1, TNR 1/3 -> 66.666... Plain mean, not weighted by rows.
    rows = _set("A", 0, tp=3, fn=1, tn=2, fp=2) + _set("RAGTruth", 100, tp=1, fn=0, tn=1, fp=2)
    board = lib.leaderboard(rows)
    assert board["RAGTruth"] == pytest.approx(200 / 3)
    assert board["average"] == pytest.approx((62.5 + 200 / 3) / 2)
    assert board["datasets_in_mean"] == 2


def test_dataset_with_one_class_is_undefined_and_left_out():
    rows = _set("A", 0, tp=3, fn=1, tn=2, fp=2) + _set("OnlyPos", 50, tp=2, fn=1, tn=0, fp=0)
    board = lib.leaderboard(rows)
    assert board["datasets"]["OnlyPos"]["balanced_accuracy"] == "undefined"
    assert board["average"] == pytest.approx(62.5)
    assert board["datasets_in_mean"] == 1
    assert board["notes"] == ["OnlyPos: one class is absent, so it is left out of the mean"]


def test_error_and_unparseable_rows_count_wrong():
    rows = [
        _row(0, "A", 1, "supported"),
        _row(1, "A", 1, "unparseable", error="unreachable"),  # positive -> fn
        _row(2, "A", 0, "unparseable"),  # negative -> fp
        _row(3, "A", 0, "unsupported"),
        _row(4, "A", 0, "unsupported", error="request-failed"),  # error wins over verdict
    ]
    counts = lib.leaderboard(rows)["datasets"]["A"]
    assert (counts["tp"], counts["fn"], counts["tn"], counts["fp"]) == (1, 1, 1, 2)
    assert (counts["errors"], counts["unparseable"]) == (2, 1)
    # TPR 1/2, TNR 1/3.
    assert counts["balanced_accuracy"] == pytest.approx(100 * (0.5 + 1 / 3) / 2)


def test_partial_file_refused_unless_allowed():
    rows = [_row(i, "A", i % 2, "supported") for i in range(3)]
    with pytest.raises(lib.ScoreError, match="3 distinct rows, not 4"):
        lib.check_complete(rows, 4)
    assert lib.check_complete(rows, 4, allow_partial=True) is True
    assert lib.check_complete(rows, 3) is False


def test_repeated_index_refused():
    rows = [_row(0, "A", 1, "supported"), _row(0, "A", 1, "supported")]
    with pytest.raises(lib.ScoreError, match="repeat"):
        lib.check_complete(rows, 1, allow_partial=True)


def test_score_results_says_partial():
    rows = _set("A", 0, 1, 0, 1, 0) + _set("RAGTruth", 10, 1, 0, 1, 0)
    header = {"kind": "header", "strategy": "clef_flash"}
    with pytest.raises(lib.ScoreError):
        lib.score_results(header, None, rows, expected=5)
    summary = lib.score_results(header, None, rows, expected=5, allow_partial=True)
    assert summary["status"] == "partial" and summary["partial"] is True
    full = lib.score_results(header, None, rows, expected=4)
    assert full["status"] == "fail" and full["partial"] is False  # 100 is 23.4 points off


@pytest.mark.parametrize(
    ("avg", "rag", "passed"),
    [
        (77.6, 84.2, True),  # exactly +1.0 on both (84.2 - 83.2 is 1.0000000000000142 in floats)
        (75.6, 82.2, True),  # exactly -1.0 on both
        (77.6001, 83.2, False),  # 1.0001 off on the average
        (76.6, 84.2001, False),  # 1.0001 off on RAGTruth
    ],
)
def test_pass_rule_boundary(avg, rag, passed):
    rule = lib.pass_rule(avg, rag, 76.6, 83.2)
    assert rule["passed"] is passed
    assert rule["average_gap"] == pytest.approx(avg - 76.6)
    assert rule["ragtruth_gap"] == pytest.approx(rag - 83.2)


def test_row_order_is_fixed_and_limit_is_a_prefix():
    first = lib.row_order(1000)
    assert first == lib.row_order(1000)
    assert lib.row_order(1000, limit=50) == first[:50]
    assert sorted(first) == list(range(1000))
    assert first[:50] != list(range(50))  # shuffled, so a limit run spans every dataset
