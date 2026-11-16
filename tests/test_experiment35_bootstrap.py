"""Experiment 35 gate bootstrap, ``bootstrap35.bootstrap_by_question`` (task 14.7).

Rules under test (pre-registration section 11.2): questions are resampled with
replacement; the bounds are the order statistics at zero-based indexes
``int(0.025 x m)`` and ``int(0.975 x m) - 1`` with no interpolation, where
``m`` is the count of values kept after the fail-closed rule; an undefined
resample takes the chance value (kappa 0, AUC 0.5) or is left out
(specificity difference); over 5% undefined, or an undefined full sample,
gives "not testable".
"""

from __future__ import annotations

import math
import random
import statistics

import pytest
from experiments._lib.stats_d6 import cohen_kappa
from tests._exp35_fixtures import load

bootstrap35 = load("bootstrap35")


def _scripted(values: list[float]):
    """A statistic that returns 0.5 on the full sample, then ``values`` one per resample."""
    calls = {"n": 0}

    def statistic(_items: list[object]) -> float:
        calls["n"] += 1
        return 0.5 if calls["n"] == 1 else values[calls["n"] - 2]

    return statistic


def _distinct(m: int, seed: int = 3) -> list[float]:
    values = [float(v) for v in range(m)]
    random.Random(seed).shuffle(values)  # noqa: S311
    return values


def test_bounds_on_10000_kept_values_are_indexes_250_and_9749() -> None:
    result = bootstrap35.bootstrap_by_question(
        [("q1", 1)], _scripted(_distinct(10_000)), n=10_000, seed=1, fill=0.0
    )
    assert (result.lower, result.upper) == (250.0, 9749.0)
    assert result.kept == 10_000
    assert result.testable


def test_bounds_on_9600_kept_values_are_indexes_240_and_9359() -> None:
    """400 undefined resamples are left out (specificity difference, ``fill=None``)."""
    values = _distinct(9_600)
    scripted = values[:]
    for position in range(0, 10_000, 25):  # 400 positions
        scripted.insert(position, math.nan)
    assert len(scripted) == 10_000
    result = bootstrap35.bootstrap_by_question(
        [("q1", 1)], _scripted(scripted), n=10_000, seed=1, fill=None
    )
    assert result.undefined == 400
    assert result.kept == 9_600
    assert (result.lower, result.upper) == (240.0, 9359.0)
    assert result.testable


def test_interpolating_rule_fails_the_index_test() -> None:
    """A linear-interpolation percentile gives other numbers on the same values."""
    values = _distinct(10_000)
    lower, upper = bootstrap35.percentile_bounds(values)
    q = statistics.quantiles(values, n=40, method="inclusive")
    assert (lower, upper) == (250.0, 9749.0)
    assert (q[0], q[-1]) != (lower, upper)


def test_undefined_resample_takes_the_fill_value_and_is_counted() -> None:
    scripted = [math.nan] * 300 + [1.0] * 9_700
    result = bootstrap35.bootstrap_by_question(
        [("q1", 1)], _scripted(scripted), n=10_000, seed=1, fill=0.0
    )
    assert result.undefined == 300
    assert result.kept == 10_000
    assert (result.lower, result.upper) == (0.0, 1.0)  # 300 zeros reach index 250


def test_600_of_10000_undefined_is_not_testable() -> None:
    scripted = [math.nan] * 600 + [1.0] * 9_400
    result = bootstrap35.bootstrap_by_question(
        [("q1", 1)], _scripted(scripted), n=10_000, seed=1, fill=0.0
    )
    assert result.undefined == 600
    assert not result.testable


def test_500_of_10000_undefined_is_still_testable() -> None:
    scripted = [math.nan] * 500 + [1.0] * 9_500
    result = bootstrap35.bootstrap_by_question(
        [("q1", 1)], _scripted(scripted), n=10_000, seed=1, fill=0.0
    )
    assert result.testable


def test_undefined_full_sample_is_not_testable() -> None:
    result = bootstrap35.bootstrap_by_question(
        [("q1", ("y", "y")), ("q2", ("y", "y"))],
        lambda items: cohen_kappa([a for a, _ in items], [b for _, b in items]),
        n=200,
        seed=1,
        fill=0.0,
    )
    assert math.isnan(result.estimate)
    assert not result.testable


def _kappa_items() -> list[tuple[str, tuple[str, str]]]:
    """40 questions with two claims each; the raters agree on most claims."""
    items = []
    rng = random.Random(11)  # noqa: S311
    for q in range(40):
        for _ in range(2):
            human = "s" if rng.random() < 0.6 else "u"
            checker = human if rng.random() < 0.85 else ("u" if human == "s" else "s")
            items.append((f"q{q:02d}", (human, checker)))
    return items


def _kappa(items: list[tuple[str, str]]) -> float:
    return cohen_kappa([a for a, _ in items], [b for _, b in items])


def test_known_kappa_fixture_gives_the_same_bounds_twice_with_one_seed() -> None:
    first = bootstrap35.bootstrap_by_question(
        _kappa_items(), _kappa, n=2_000, seed=20261125, fill=0.0
    )
    second = bootstrap35.bootstrap_by_question(
        _kappa_items(), _kappa, n=2_000, seed=20261125, fill=0.0
    )
    assert first == second
    assert first.estimate == pytest.approx(_kappa([v for _, v in _kappa_items()]))
    assert first.lower < first.estimate < first.upper


def test_resampling_unit_is_the_question() -> None:
    """Every resample holds whole questions: both claims of a drawn question come together."""
    seen: list[list[str]] = []

    def statistic(items: list[tuple[str, str]]) -> float:
        seen.append([claim for claim, _ in items])
        return 0.0

    items = [(f"q{q}", (f"q{q}-c{c}", "x")) for q in range(5) for c in range(2)]
    bootstrap35.bootstrap_by_question(items, statistic, n=20, seed=4, fill=0.0)
    for sample in seen[1:]:
        assert len(sample) == 10
        for claim in sample:
            if claim.endswith("-c0"):
                assert claim.replace("-c0", "-c1") in sample


def test_input_order_does_not_change_the_result() -> None:
    items = _kappa_items()
    shuffled = items[:]
    random.Random(2).shuffle(shuffled)  # noqa: S311
    a = bootstrap35.bootstrap_by_question(items, _kappa, n=500, seed=9, fill=0.0)
    b = bootstrap35.bootstrap_by_question(shuffled, _kappa, n=500, seed=9, fill=0.0)
    assert (a.lower, a.upper) == (b.lower, b.upper)
