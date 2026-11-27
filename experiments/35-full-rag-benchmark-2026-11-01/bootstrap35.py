"""Gate bootstrap for Experiment 35: resample questions, percentile bounds, fail closed.

One function, :func:`bootstrap_by_question`, gives every gate interval of
pre-registration section 11.2 (kappa, AUC lower bound, specificity
difference). :func:`bootstrap_many` gives several statistics on one set of
resamples (the specificity and sensitivity differences). They are not in
``experiments/_lib/stats.py`` or ``stats_d6.py`` (task 14.7, design D35 as
amended by D39, finding H-16).

The rules:

- The resampling unit is the question. All items of a drawn question come
  into the resample together.
- An undefined resample (the statistic returns NaN) is never drawn again. It
  is counted once. With ``fill`` set it takes that value (kappa 0, AUC 0.5);
  with ``fill=None`` it is left out (specificity difference).
- An undefined full sample, or more than 5% undefined resamples, makes the
  result not testable.
- The bounds use the order-statistic rule of ``stats_d6.paired_bootstrap``:
  sort the kept values in ascending order, take the lower bound at zero-based
  index ``int(0.025 x m)`` and the upper bound at ``int(0.975 x m) - 1``, with
  no interpolation. ``m`` is the count of kept values.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BootResult:
    """One bootstrap result.

    Attributes:
        estimate: The statistic on the full sample (NaN when undefined).
        lower: Lower 95% bound (NaN when not testable).
        upper: Upper 95% bound (NaN when not testable).
        n: Number of resamples drawn.
        undefined: Number of resamples on which the statistic was undefined.
        kept: Number of values the bounds use (``m``).
        testable: False when the full sample is undefined or over 5% of
            resamples are undefined.
    """

    estimate: float
    lower: float
    upper: float
    n: int
    undefined: int
    kept: int
    testable: bool

    def as_dict(self) -> dict[str, Any]:
        """Return the result as a JSON-ready dict (NaN written as None)."""
        out: dict[str, Any] = {}
        for name in ("estimate", "lower", "upper", "n", "undefined", "kept", "testable"):
            value = getattr(self, name)
            out[name] = None if isinstance(value, float) and math.isnan(value) else value
        return out


def percentile_bounds(values: Sequence[float]) -> tuple[float, float]:
    """Return the 95% percentile bounds by the order-statistic rule.

    Args:
        values: The kept resample values (any order).

    Returns:
        The values at zero-based indexes ``int(0.025 x m)`` and
        ``int(0.975 x m) - 1`` of the sorted values.
    """
    ordered = sorted(values)
    m = len(ordered)
    return ordered[int(0.025 * m)], ordered[int(0.975 * m) - 1]


def bootstrap_by_question(
    items: Sequence[tuple[Hashable, Any]],
    statistic: Callable[[list[Any]], float],
    *,
    n: int,
    seed: int,
    fill: float | None,
) -> BootResult:
    """Return the statistic and its percentile bootstrap 95% interval by question.

    Args:
        items: ``(question_id, item)`` pairs. Items of one question are
            resampled together. Question IDs must sort (strings or tuples).
        statistic: Takes the list of items of one sample and returns a
            float, or NaN when the statistic is undefined on that sample.
        n: Number of resamples (10,000 for every gate).
        seed: Seed of the resampling draw (pre-registration section 16).
        fill: Value an undefined resample takes (0.0 for kappa, 0.5 for
            AUC), or None to leave it out (specificity difference).

    Returns:
        The :class:`BootResult`.
    """
    return bootstrap_many(items, {"value": statistic}, n=n, seed=seed, fill=fill)["value"]


def bootstrap_many(
    items: Sequence[tuple[Hashable, Any]],
    statistics: Mapping[str, Callable[[list[Any]], float]],
    *,
    n: int,
    seed: int,
    fill: float | None,
) -> dict[str, BootResult]:
    """Return each statistic's bootstrap result on one set of resamples by question.

    Every statistic sees the same drawn questions. Each keeps its own
    undefined count, and the fail-closed rules apply to each on its own.

    Args:
        items: As :func:`bootstrap_by_question`.
        statistics: Name to statistic, each as :func:`bootstrap_by_question`.
        n: Number of resamples.
        seed: Seed of the resampling draw.
        fill: As :func:`bootstrap_by_question`, for every statistic.

    Returns:
        Name to :class:`BootResult`.
    """
    groups: dict[Hashable, list[Any]] = defaultdict(list)
    for question, item in items:
        groups[question].append(item)
    questions = sorted(groups)  # never dict or file order
    units = [groups[q] for q in questions]
    full = [item for unit in units for item in unit]
    estimates = {name: stat(full) for name, stat in statistics.items()}
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    values: dict[str, list[float]] = {name: [] for name in statistics}
    undefined = dict.fromkeys(statistics, 0)
    for _ in range(n):
        drawn = [item for _ in units for item in rng.choice(units)]
        for name, stat in statistics.items():
            value = stat(drawn)
            if math.isnan(value):
                undefined[name] += 1
                if fill is None:
                    continue
                value = fill
            values[name].append(value)
    out = {}
    for name in statistics:
        kept = values[name]
        testable = not math.isnan(estimates[name]) and undefined[name] * 20 <= n and bool(kept)
        lower, upper = percentile_bounds(kept) if testable else (math.nan, math.nan)
        out[name] = BootResult(
            estimates[name], lower, upper, n, undefined[name], len(kept), testable
        )
    return out
