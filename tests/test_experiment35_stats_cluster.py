"""Clustered analysis of Experiment 35 (readiness task 15.6, pre-registration section 9).

Every expected value is worked by hand in a comment, or comes from scipy or
statsmodels on the same fixture, or from a plain loop written here.
"""

from __future__ import annotations

import itertools
import math
import random
import subprocess

import numpy as np
import pytest
from experiments._lib import stats_cluster as sc
from scipy import stats as scipy_stats


def test_closed_form_hand_case() -> None:
    # d = 1, 2, 3, 4: mean 2.5, residuals -1.5, -0.5, 0.5, 1.5, sum of squares 5.
    # variance = 5 x (4/3)^2 / 16 = 5/9; t = 2.5 / sqrt(5/9) on 3 degrees of freedom.
    result = sc.cluster_test([1.0, 2.0, 3.0, 4.0])
    assert result.estimate == pytest.approx(2.5)
    assert result.variance == pytest.approx(5 / 9, abs=1e-12)
    assert result.df == 3
    t = 2.5 / math.sqrt(5 / 9)
    assert result.p_value == pytest.approx(2 * scipy_stats.t.sf(t, 3), abs=1e-12)
    half = 3.182446305284263 * math.sqrt(5 / 9)  # t(0.975, 3) from tables
    assert result.ci_low == pytest.approx(2.5 - half, abs=1e-9)
    assert result.ci_high == pytest.approx(2.5 + half, abs=1e-9)


def test_closed_form_equals_paired_t_variance_times_n_over_n_minus_1() -> None:
    rng = random.Random(7)  # noqa: S311
    d = [rng.gauss(0.03, 0.2) for _ in range(30)]
    t_paired = scipy_stats.ttest_1samp(d, 0.0).statistic
    paired_variance = (np.mean(d) / t_paired) ** 2
    assert sc.cluster_test(d).variance == pytest.approx(paired_variance * 30 / 29, rel=1e-12)


def test_gee_estimate_and_variance_equal_closed_form_on_seeded_fixture() -> None:
    rng = random.Random(20261114)  # noqa: S311
    d = [rng.gauss(0.02, 0.2) for _ in range(30)]
    closed = sc.closed_form(d)
    library = sc.gee_fit(d)
    assert library[0] == pytest.approx(closed[0], abs=1e-10)
    assert library[1] == pytest.approx(closed[1], abs=1e-10)
    result = sc.cluster_test(d)
    assert result.source == "statsmodels"
    assert result.library_difference <= 1e-10


def test_document_clusters_hand_case() -> None:
    # d = 1, 2, 3, 4 in documents a, a, b, c. N = 4, mean 2.5.
    # Cluster sums of residuals: a = -2 (2 questions), b = 0.5, c = 1.5.
    # Bias-reduced: (-2 / (1 - 2/4))^2 + (0.5 / 0.75)^2 + (1.5 / 0.75)^2 = 16 + 4/9 + 4.
    # variance = that / 16; t on 3 documents minus 1 = 2 degrees of freedom.
    result = sc.cluster_test([1.0, 2.0, 3.0, 4.0], clusters=["a", "a", "b", "c"])
    assert result.variance == pytest.approx((16 + 4 / 9 + 4) / 16, abs=1e-12)
    assert result.df == 2
    assert result.n_clusters == 3
    assert result.source == "statsmodels"


def test_zero_estimate_and_zero_variance_gives_p_one() -> None:
    result = sc.cluster_test([0.0] * 12)
    assert result.estimate == 0.0
    assert result.variance == 0.0
    assert result.p_value == 1.0
    assert result.source == "closed form"  # the library cannot fit constant data


def test_one_cluster_gives_nan_p_value() -> None:
    assert math.isnan(sc.cluster_test([0.3]).p_value)
    assert math.isnan(sc.cluster_test([0.1, 0.2], clusters=["a", "a"]).p_value)


def test_t_reference_not_normal() -> None:
    d = [0.1, 0.3, -0.05, 0.2, 0.15, 0.4]
    result = sc.cluster_test(d)
    z_p = 2 * scipy_stats.norm.sf(abs(result.estimate) / math.sqrt(result.variance))
    assert result.p_value > z_p  # t on 5 degrees of freedom has heavier tails


def _enumerated_signs(n_documents: int) -> np.ndarray:
    return np.array(list(itertools.product((1, -1), repeat=n_documents)), dtype=np.int8)


def test_sign_flip_hand_case_with_all_sign_patterns() -> None:
    # Three documents, one question each, d = 1, 1, 1. Observed statistic 1.
    # Of the 8 sign patterns, 2 give |statistic| 1 and 6 give 1/3. p = (1 + 2) / 9.
    flip = sc.SignFlip([1.0, 1.0, 1.0], ["a", "b", "c"], _enumerated_signs(3))
    assert flip.p_value(0.0) == pytest.approx(3 / 9)


def test_sign_flip_question_weighted_statistic() -> None:
    # Document a holds d = 0.2 and 0.4, document b holds 0.6. Statistic = 1.2 / 3.
    flip = sc.SignFlip([0.2, 0.4, 0.6], ["a", "a", "b"], _enumerated_signs(2))
    assert flip.estimate == pytest.approx(0.4)
    # Patterns (+,+) and (-,-) give |0.4|; (+,-) and (-,+) give |0.6 - 0.6| / 3 = 0.
    assert flip.p_value(0.0) == pytest.approx((1 + 2) / 5)


def test_tie_tolerance_is_one_e_minus_12() -> None:
    draws = np.array([0.5 - 5e-13, 0.5 - 2e-12, -0.5, 0.1])
    # 0.5 - 5e-13 and -0.5 count; 0.5 - 2e-12 and 0.1 do not.
    assert sc.count_at_least(0.5, draws) == 2


def test_sign_flip_same_seed_same_result() -> None:
    rng = random.Random(3)  # noqa: S311
    d = [rng.gauss(0.05, 0.2) for _ in range(40)]
    docs = [f"doc{i // 2}" for i in range(40)]
    first = sc.sign_flip_test(d, docs, n_draws=5000)
    second = sc.sign_flip_test(d, docs, n_draws=5000)
    assert first == second
    assert first.seed == 20261101


def test_sign_flip_zero_data_gives_p_one() -> None:
    result = sc.sign_flip_test([0.0] * 10, [f"d{i}" for i in range(10)], n_draws=2000)
    assert result.p_value == 1.0


def _naive_p(d: list[float], docs: list[str], signs: np.ndarray, shift: float) -> float:
    """A plain loop over draws, written apart from the module, for the scan below."""
    names = sorted(set(docs))
    sums = [sum(x - shift for x, g in zip(d, docs, strict=True) if g == name) for name in names]
    observed = abs(sum(sums) / len(d))
    hits = 0
    for row in signs:
        value = abs(sum(int(s) * v for s, v in zip(row, sums, strict=True)) / len(d))
        if value >= observed - 1e-12:
            hits += 1
    return (1 + hits) / (len(signs) + 1)


def test_sign_flip_interval_ends_match_a_naive_grid_scan() -> None:
    rng = random.Random(11)  # noqa: S311
    d = [rng.gauss(0.1, 0.15) for _ in range(24)]
    docs = [f"doc{i // 2}" for i in range(24)]
    signs = np.random.default_rng(5).integers(0, 2, size=(200, 12), dtype=np.int8) * 2 - 1
    flip = sc.SignFlip(d, docs, signs)
    low, high = flip.interval(0.05, 1e-4)
    # Known answer: the lowest and highest shift the naive loop does not reject.
    # A coarse scan (step 1e-3 over plus or minus 0.3) finds each end, then a fine
    # scan (step 1e-5) within 1e-3 of it.
    coarse = [flip.estimate + k * 1e-3 for k in range(-300, 301)]
    kept = [g for g in coarse if _naive_p(d, docs, signs, g) >= 0.05]
    fine_low = [min(kept) + k * 1e-5 for k in range(-100, 101)]
    fine_high = [max(kept) + k * 1e-5 for k in range(-100, 101)]
    naive_low = min(g for g in fine_low if _naive_p(d, docs, signs, g) >= 0.05)
    naive_high = max(g for g in fine_high if _naive_p(d, docs, signs, g) >= 0.05)
    assert low == pytest.approx(naive_low, abs=1.5e-4)
    assert high == pytest.approx(naive_high, abs=1.5e-4)
    # The ends are not rejected; 1e-4 further out is rejected.
    assert flip.p_value(low) >= 0.05 and flip.p_value(low - 1e-4) < 0.05
    assert flip.p_value(high) >= 0.05 and flip.p_value(high + 1e-4) < 0.05


def test_gee_type_one_error_near_005_with_unequal_cell_variance() -> None:
    # FreshStack-sized: 203 questions; each d is the mean of three cells minus the mean
    # of three others, every cell with its own error SD and no true effect.
    rng = np.random.default_rng(20261114)
    sds = np.array([0.05, 0.1, 0.3, 0.15, 0.2, 0.25])
    rejected = 0
    for _ in range(2000):
        cells = rng.normal(0.0, sds, size=(203, 6)) + rng.normal(0.5, 0.2, size=(203, 1))
        d = cells[:, :3].mean(axis=1) - cells[:, 3:].mean(axis=1)
        rejected += sc.cluster_test(d.tolist()).p_value < 0.05
    rate = rejected / 2000
    assert 0.035 <= rate <= 0.065, rate  # 0.05 plus or minus 3 standard errors (0.0049)


def test_sign_flip_type_one_error_near_005() -> None:
    # 84 documents, about 1.8 questions each, a document effect per cell, unequal cell SD.
    rng = np.random.default_rng(20261115)
    sizes = rng.choice([1, 2, 3], size=84, p=[0.4, 0.4, 0.2])
    docs = [f"d{j}" for j, m in enumerate(sizes) for _ in range(m)]
    owner = np.repeat(np.arange(84), sizes)
    rejected = 0
    for sim in range(2000):
        doc_effect = rng.normal(0.0, [0.1, 0.25], size=(84, 2))[owner]
        noise = rng.normal(0.0, [0.05, 0.2], size=(len(docs), 2))
        d = (doc_effect + noise) @ np.array([1.0, -1.0])
        rejected += sc.sign_flip_test(d.tolist(), docs, n_draws=1000, seed=sim).p_value < 0.05
    rate = rejected / 2000
    assert 0.035 <= rate <= 0.065, rate


def test_stats_group_stays_out_of_the_app_install() -> None:
    exported = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-group", "stats", "--no-hashes"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "statsmodels" not in exported
    with_group = subprocess.run(
        ["uv", "export", "--frozen", "--only-group", "stats", "--no-hashes"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "statsmodels==0.15.0" in with_group
