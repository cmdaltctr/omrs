"""Differential-error statistics of the faithfulness gate (A18; pre-registration 11.2).

The GLM-5.3 specificity difference and the sensitivity difference (2,048 minus
512) come from one set of resamples by question (seed 20261126). The rule
fires when either 95% interval excludes zero. An undefined statistic fails
closed as :mod:`bootstrap35` describes. ``Rows`` here are
``(chunk_size, human_supported, checker_supported)``.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Any

from bootstrap35 import BootResult, percentile_bounds

Rows = Sequence[tuple[int, bool, bool]]


def _rate(calls: list[bool]) -> float:
    return sum(calls) / len(calls) if calls else math.nan


def specificity(rows: Rows, level: int) -> float:
    """Share of human-supported claims at *level* the checker calls supported (NaN when none)."""
    return _rate([checker for c, human, checker in rows if c == level and human])


def sensitivity(rows: Rows, level: int) -> float:
    """Share of human-unsupported claims at *level* called unsupported (NaN when none)."""
    return _rate([not checker for c, human, checker in rows if c == level and not human])


def specificity_difference(rows: Rows) -> float:
    """Specificity at 2,048 minus specificity at 512."""
    return specificity(rows, 2048) - specificity(rows, 512)


def sensitivity_difference(rows: Rows) -> float:
    """Sensitivity at 2,048 minus sensitivity at 512."""
    return sensitivity(rows, 2048) - sensitivity(rows, 512)


def paired_bootstrap(
    items: Sequence[tuple[Hashable, Any]],
    statistics: Mapping[str, Callable[[list[Any]], float]],
    *,
    n: int,
    seed: int,
) -> dict[str, BootResult]:
    """Return each statistic's percentile bootstrap on one set of resamples by question.

    Every statistic sees the same drawn questions. An undefined resample of a
    statistic is left out of that statistic and counted once; more than 5%
    undefined, or an undefined full sample, makes it not testable.

    Args:
        items: ``(question_id, item)`` pairs; a question's items are resampled together.
        statistics: Name to statistic (NaN when undefined on a sample).
        n: Number of resamples.
        seed: Seed of the resampling draw.

    Returns:
        Name to :class:`bootstrap35.BootResult`.
    """
    groups: dict[Hashable, list[Any]] = defaultdict(list)
    for question, item in items:
        groups[question].append(item)
    units = [groups[q] for q in sorted(groups)]
    full = [item for unit in units for item in unit]
    estimates = {name: stat(full) for name, stat in statistics.items()}
    values: dict[str, list[float]] = {name: [] for name in statistics}
    undefined = dict.fromkeys(statistics, 0)
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    for _ in range(n):
        drawn = [item for _ in units for item in rng.choice(units)]
        for name, stat in statistics.items():
            value = stat(drawn)
            if math.isnan(value):
                undefined[name] += 1
            else:
                values[name].append(value)
    out = {}
    for name in statistics:
        ok = not math.isnan(estimates[name]) and undefined[name] * 20 <= n and bool(values[name])
        low, high = percentile_bounds(values[name]) if ok else (math.nan, math.nan)
        out[name] = BootResult(
            estimates[name], low, high, n, undefined[name], len(values[name]), ok
        )
    return out


def excludes_zero(result: BootResult) -> bool:
    """True when a testable 95% interval lies wholly on one side of zero."""
    return result.testable and (result.lower > 0 or result.upper < 0)
