"""Checks for the paired statistics module. Copy next to it in ``experiments/_lib/``.

Expected values were cross-checked against scipy and statsmodels.
"""

# ruff: noqa: S101

from __future__ import annotations

import pytest

from . import stats


def test_wilson_matches_statsmodels() -> None:
    lo, hi = stats.wilson(56, 76)
    assert lo == pytest.approx(0.628188, abs=1e-6)
    assert hi == pytest.approx(0.822706, abs=1e-6)


def test_mcnemar_matches_binomial_test() -> None:
    a = [True] * 18 + [False] * 25 + [True] * 10
    b = [False] * 18 + [True] * 25 + [True] * 10
    assert stats.mcnemar_exact(a, b, one_sided=True) == pytest.approx(0.180189, abs=1e-6)
    assert stats.mcnemar_exact(a, b) == pytest.approx(0.360378, abs=1e-6)


def test_identical_arms_show_no_difference() -> None:
    result = stats.compare([0.5, 0.7], [0.5, 0.7], level="medium")
    assert result["difference"] == 0
    assert result["p_value"] == 1.0


def test_clear_gain_has_positive_range() -> None:
    a = [0.2 + i / 100 for i in range(40)]
    b = [x + 0.1 for x in a]
    result = stats.compare(a, b, level="expert", metric="nDCG@10")
    lo, hi = result["difference_range"]
    assert lo > 0 and hi > 0
    assert "very likely positive" in result["sentences"][2]


def test_holm_keeps_order() -> None:
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_unpaired_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        stats.win_loss([1.0], [1.0, 2.0])
