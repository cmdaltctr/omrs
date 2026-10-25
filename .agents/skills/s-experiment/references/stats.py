"""Shared paired statistics for experiments. Copy into ``experiments/_lib/`` (see SKILL.md first).

Standard library only. Every function takes per-item values for two arms
measured on the same items (a paired design), in the same order.

Levels (set ``"stats"`` in ``plan.json``):

* ``basic``: counts, means, difference, wins/losses/ties.
* ``medium``: basic, plus 95% ranges and one paired test.
* ``expert``: medium, plus the smallest detectable gain.
  Use ``holm`` yourself when there is more than one primary test.

``compare`` returns numbers and one plain-English sentence per number, so a
summariser can paste the sentences under the report tables.
"""

# Skill copy, not package code: _check_paired guards zip lengths; random is for resampling.
# ruff: noqa: B905, E501, S311

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from statistics import NormalDist, fmean, stdev

LEVELS = ("basic", "medium", "expert")


def wilson(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Return the Wilson interval for a rate.

    Args:
        successes: Number of items that count as a success.
        n: Number of items.
        confidence: Interval confidence, for example 0.95.

    Returns:
        Lower and upper bounds, from 0 to 1.
    """
    if n == 0:
        return (0.0, 1.0)
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def win_loss(a: Sequence[float], b: Sequence[float]) -> dict[str, int]:
    """Count items where the candidate ``b`` beats, loses to or ties ``a``.

    Args:
        a: Baseline values per item.
        b: Candidate values per item, same order.

    Returns:
        Counts under the keys ``wins``, ``losses`` and ``ties``.
    """
    _check_paired(a, b)
    wins = sum(1 for x, y in zip(a, b) if y > x)
    losses = sum(1 for x, y in zip(a, b) if y < x)
    return {"wins": wins, "losses": losses, "ties": len(a) - wins - losses}


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool], one_sided: bool = False) -> float:
    """Return the exact McNemar p-value for paired yes/no outcomes.

    Only items where the arms disagree carry information.

    Args:
        a: Baseline outcomes per item.
        b: Candidate outcomes per item, same order.
        one_sided: Test only "candidate better" when True.

    Returns:
        The p-value.
    """
    _check_paired(a, b)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    n = only_a + only_b
    if n == 0:
        return 1.0
    if one_sided:
        tail = sum(math.comb(n, k) for k in range(only_b, n + 1))
        return min(1.0, tail / 2**n)
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, 2 * tail / 2**n)


def paired_permutation(
    a: Sequence[float],
    b: Sequence[float],
    n_perm: int = 10_000,
    seed: int = 0,
) -> float:
    """Return a two-sided paired permutation (randomisation) p-value.

    Each shuffle flips the sign of each per-item difference at random.

    Args:
        a: Baseline values per item.
        b: Candidate values per item, same order.
        n_perm: Number of shuffles.
        seed: Random seed, recorded in ``plan.json``.

    Returns:
        The p-value.
    """
    _check_paired(a, b)
    diffs = [y - x for x, y in zip(a, b)]
    observed = abs(sum(diffs))
    if observed == 0:
        return 1.0
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        total = sum(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(total) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    groups: Sequence[str] | None = None,
    n_boot: int = 10_000,
    seed: int = 0,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Return the mean difference ``b - a`` and its bootstrap interval.

    With ``groups``, whole groups are resampled (for example all pages of
    one document), so grouped items do not look more independent than they
    are.

    Args:
        a: Baseline values per item.
        b: Candidate values per item, same order.
        groups: Optional group label per item.
        n_boot: Number of resamples.
        seed: Random seed, recorded in ``plan.json``.
        confidence: Interval confidence.

    Returns:
        The mean difference, the lower bound and the upper bound.
    """
    _check_paired(a, b)
    diffs = [y - x for x, y in zip(a, b)]
    if not diffs:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    if groups is None:
        units = [[d] for d in diffs]
    else:
        if len(groups) != len(diffs):
            raise ValueError("groups must have one label per item")
        by_group: dict[str, list[float]] = defaultdict(list)
        for g, d in zip(groups, diffs):
            by_group[g].append(d)
        units = list(by_group.values())
    means = []
    for _ in range(n_boot):
        sample = [d for _ in units for d in rng.choice(units)]
        means.append(fmean(sample))
    means.sort()
    lo_i = int((1 - confidence) / 2 * n_boot)
    hi_i = int((1 + confidence) / 2 * n_boot) - 1
    return (fmean(diffs), means[lo_i], means[hi_i])


def holm(p_values: Sequence[float]) -> list[float]:
    """Return Holm-adjusted p-values, in the input order.

    Args:
        p_values: One p-value per primary test.

    Returns:
        Adjusted p-values. Compare each with 0.05.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def min_detectable_effect(
    sd_of_differences: float,
    n: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Return the smallest mean difference the design can detect.

    Use pilot data or an earlier experiment for ``sd_of_differences``.

    Args:
        sd_of_differences: Standard deviation of per-item differences.
        n: Number of items (or groups, if items are grouped).
        alpha: Two-sided significance level.
        power: Chance of detecting a true effect of this size.

    Returns:
        The minimum detectable effect, in the metric's own units.
    """
    if n <= 0:
        return math.inf
    z = NormalDist()
    return (z.inv_cdf(1 - alpha / 2) + z.inv_cdf(power)) * sd_of_differences / math.sqrt(n)


def compare(
    a: Sequence[float],
    b: Sequence[float],
    *,
    level: str = "medium",
    binary: bool = False,
    metric: str = "score",
    groups: Sequence[str] | None = None,
    seed: int = 0,
    points: bool = True,
) -> dict[str, object]:
    """Compare a candidate ``b`` with a baseline ``a`` at one stats level.

    Args:
        a: Baseline values per item (bools when ``binary``).
        b: Candidate values per item, same order.
        level: ``basic``, ``medium`` or ``expert``.
        binary: True for yes/no outcomes.
        metric: Metric name used in the sentences.
        groups: Optional group label per item.
        seed: Random seed for resampling.
        points: Show differences in points (x100) for 0-1 metrics.

    Returns:
        A dict of numbers plus ``sentences``, a list of plain sentences.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    _check_paired(a, b)
    xs = [float(v) for v in a]
    ys = [float(v) for v in b]
    n = len(xs)
    scale, unit = (100.0, " points") if points else (1.0, "")
    out: dict[str, object] = {"level": level, "metric": metric, "n": n}
    sentences: list[str] = []

    mean_a, mean_b = fmean(xs), fmean(ys)
    diff = mean_b - mean_a
    wl = win_loss(xs, ys)
    out.update({"baseline": mean_a, "candidate": mean_b, "difference": diff, **wl})
    if binary:
        ka, kb = int(sum(xs)), int(sum(ys))
        gap = kb - ka
        compared = (
            "the same as the baseline"
            if gap == 0
            else f"{abs(gap)} {'more' if gap > 0 else 'fewer'} than the baseline"
        )
        sentences.append(
            f"The candidate got {kb} of {n} right on {metric}, {compared} ({ka} of {n})."
        )
    else:
        sentences.append(
            f"Mean {metric} was {mean_b:.3f} for the candidate and {mean_a:.3f} "
            f"for the baseline, a difference of {_signed(diff * scale, 1)}{unit}."
        )
    sentences.append(
        f"The candidate won on {wl['wins']} items, lost on {wl['losses']} and tied on {wl['ties']}."
    )

    if level in ("medium", "expert"):
        if binary:
            out["baseline_range"] = wilson(int(sum(xs)), n)
            out["candidate_range"] = wilson(int(sum(ys)), n)
            p = mcnemar_exact([bool(v) for v in xs], [bool(v) for v in ys])
            out["test"] = "mcnemar_exact"
        else:
            p = paired_permutation(xs, ys, seed=seed)
            out["test"] = "paired_permutation"
        _, lo, hi = paired_bootstrap(xs, ys, groups=groups, seed=seed)
        out.update({"p_value": p, "difference_range": (lo, hi)})
        lo_s, hi_s = lo * scale, hi * scale
        if lo > 0 or hi < 0:
            direction = "positive" if lo > 0 else "negative"
            sentences.append(
                f"The 95% range for the difference is {lo_s:.1f} to {hi_s:.1f}{unit}, "
                f"so the true difference is very likely {direction}."
            )
        else:
            sentences.append(
                f"The 95% range for the difference is {lo_s:.1f} to {hi_s:.1f}{unit}. "
                "It includes zero, so this data cannot show whether the change helps."
            )
        sentences.append(_p_sentence(p))

    if level == "expert":
        diffs = [y - x for x, y in zip(xs, ys)]
        units_n = len(set(groups)) if groups is not None else n
        sd = stdev(diffs) if n > 1 else 0.0
        mde = min_detectable_effect(sd, units_n)
        out["min_detectable_effect"] = mde
        sentences.append(
            f"With {units_n} {'groups' if groups is not None else 'items'}, this design "
            f"can only detect differences of about {mde * scale:.1f}{unit} or more."
        )

    out["sentences"] = sentences
    return out


def _p_sentence(p: float) -> str:
    if p < 0.001:
        return f"A difference this large would almost never happen by chance (p = {p:.4f})."
    if p >= 0.2:
        return f"A difference this size often happens by chance alone (p = {p:.3f})."
    return f"A difference this large would happen by chance about 1 time in {round(1 / p)} (p = {p:.3f})."


def _signed(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f}"


def _check_paired(a: Sequence[object], b: Sequence[object]) -> None:
    if len(a) != len(b):
        raise ValueError(f"paired arms need the same length, got {len(a)} and {len(b)}")
