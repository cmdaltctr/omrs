"""Clustered tests for Experiment 35 (pre-registration section 9, readiness task 15.6).

Two decision tests on per-question contrast scores ``d``:

- ``cluster_test``: the bias-reduced sandwich test of section 9 point 3
  (Mancl and DeRouen 2001), t reference on clusters minus 1 degrees of
  freedom. With no ``clusters`` every question is its own cluster (FreshStack,
  BioASQ, Legal). With document clusters it is the FinanceBench sensitivity
  check of point 6. ``statsmodels`` GEE gives the estimate and the variance;
  the closed form checks it, and the closed form is used when they differ.
- ``sign_flip_test``: the FinanceBench document-level sign-flip permutation
  test of point 4, with the interval found by inverting the same test.

The p-value and the interval always come from this module, never from the
library's default normal reference.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as scipy_stats

SIGN_FLIP_SEED = 20261101
SIGN_FLIP_DRAWS = 100_000
TIE_TOLERANCE = 1e-12
LIBRARY_TOLERANCE = 1e-10
_MAX_SHIFT = 1e6

__all__ = [
    "ClusterResult",
    "SignFlip",
    "SignFlipResult",
    "closed_form",
    "cluster_test",
    "count_at_least",
    "gee_fit",
    "sign_flip_test",
]


@dataclass(frozen=True)
class ClusterResult:
    """One bias-reduced cluster test.

    Attributes:
        estimate: Plain mean of ``d``.
        variance: Bias-reduced sandwich variance of the estimate.
        df: Degrees of freedom of the t reference (clusters minus 1).
        p_value: Two-sided p-value from the t reference.
        ci_low: Lower end of the 95% interval.
        ci_high: Upper end of the 95% interval.
        n: Number of questions.
        n_clusters: Number of clusters.
        source: ``statsmodels`` when the library matched the closed form, else
            ``closed form``.
        library_difference: Largest absolute difference between the library and
            the closed form, over estimate and variance (NaN when the variance
            is zero and the library is not run, or when it gave no number).
    """

    estimate: float
    variance: float
    df: int
    p_value: float
    ci_low: float
    ci_high: float
    n: int
    n_clusters: int
    source: str
    library_difference: float


def _labels(n: int, clusters: Sequence[Hashable] | None) -> list[Hashable]:
    if clusters is None:
        return list(range(n))
    if len(clusters) != n:
        raise ValueError(f"need one cluster label per score, got {len(clusters)} for {n}")
    return list(clusters)


def closed_form(
    d: Sequence[float], clusters: Sequence[Hashable] | None = None
) -> tuple[float, float, int]:
    """Return the estimate, the bias-reduced variance and the number of clusters.

    For an intercept-only model the leverage of cluster j is m_j / N, so its
    corrected residual sum is R_j / (1 - m_j / N). The variance is the sum of
    their squares over N squared. With one question per cluster this is
    (sum of r_q squared) x (n / (n - 1)) squared / n squared (section 9 point 3).

    Args:
        d: Per-question contrast scores.
        clusters: Optional cluster label per score; ``None`` makes each question
            its own cluster.

    Returns:
        The estimate, the variance and the number of clusters.
    """
    n = len(d)
    estimate = math.fsum(d) / n
    sums: dict[Hashable, list[float]] = {}
    for value, label in zip(d, _labels(n, clusters), strict=True):
        sums.setdefault(label, []).append(value - estimate)
    if len(sums) < 2:  # one cluster has leverage 1: no variance estimate
        return estimate, math.nan, len(sums)
    total = 0.0
    for residuals in sums.values():
        total += (math.fsum(residuals) / (1 - len(residuals) / n)) ** 2
    return estimate, total / n**2, len(sums)


def gee_fit(d: Sequence[float], clusters: Sequence[Hashable] | None = None) -> tuple[float, float]:
    """Fit ``statsmodels`` GEE of ``d`` on an intercept and return estimate and variance.

    Gaussian family, identity link, independence working correlation,
    ``cov_type="bias_reduced"`` (section 9 point 3).

    Args:
        d: Per-question contrast scores.
        clusters: Optional cluster label per score; ``None`` makes each question
            its own cluster.

    Returns:
        The estimate and its variance, as the library reports them.
    """
    import statsmodels.api as sm
    from statsmodels.tools.sm_exceptions import PerfectSeparationWarning

    labels = _labels(len(d), clusters)
    codes = {label: i for i, label in enumerate(dict.fromkeys(labels))}
    model = sm.GEE(
        np.asarray(d, dtype=float),
        np.ones((len(d), 1)),
        groups=np.array([codes[label] for label in labels]),
        family=sm.families.Gaussian(),
        cov_struct=sm.cov_struct.Independence(),
    )
    # Near-constant d (rounding noise only) trips the GLM start-value warning;
    # the closed-form comparison in cluster_test guards the numbers.
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", PerfectSeparationWarning)
        fit = model.fit(cov_type="bias_reduced")
    return float(fit.params[0]), float(fit.cov_params()[0, 0])


def cluster_test(d: Sequence[float], clusters: Sequence[Hashable] | None = None) -> ClusterResult:
    """Run the bias-reduced cluster test with a t reference on clusters minus 1.

    A row whose estimate and variance are both zero gets p = 1 (section 9
    point 5). A non-zero estimate with zero variance gets p = 0. Fewer than two
    clusters give a NaN p-value, which the caller must stop on.

    Args:
        d: Per-question contrast scores.
        clusters: Optional cluster label per score.

    Returns:
        The test result.
    """
    estimate, variance, n_clusters = closed_form(d, clusters)
    source, difference = "closed form", math.nan
    if variance > 0:  # GEE raises on constant data, so the library is not run there
        gee_estimate, gee_variance = gee_fit(d, clusters)
        difference = max(abs(gee_estimate - estimate), abs(gee_variance - variance))
    if difference <= LIBRARY_TOLERANCE:
        estimate, variance, source = gee_estimate, gee_variance, "statsmodels"
    df = n_clusters - 1
    if df < 1:
        p_value, half = math.nan, math.nan
    elif variance == 0:
        p_value, half = (1.0 if estimate == 0 else 0.0), 0.0
    else:
        se = math.sqrt(variance)
        p_value = float(2 * scipy_stats.t.sf(abs(estimate) / se, df))
        half = float(scipy_stats.t.ppf(0.975, df)) * se
    return ClusterResult(
        estimate=estimate,
        variance=variance,
        df=df,
        p_value=p_value,
        ci_low=estimate - half,
        ci_high=estimate + half,
        n=len(d),
        n_clusters=n_clusters,
        source=source,
        library_difference=difference,
    )


def count_at_least(observed: float, draws: np.ndarray) -> int:
    """Count draws whose absolute value is at least ``|observed|`` minus 1e-12.

    The 1e-12 tie tolerance is part of the registered test (section 9 point 4).

    Args:
        observed: The observed statistic.
        draws: The statistic under each sign draw.

    Returns:
        The number of draws at least as large.
    """
    return int(np.count_nonzero(np.abs(draws) >= abs(observed) - TIE_TOLERANCE))


class SignFlip:
    """Document-level sign-flip test on a fixed set of sign draws.

    Column j of ``signs`` belongs to the j-th document ID in sorted order.
    The statistic is the question-weighted mean of ``d``. A shift ``delta`` is
    tested by subtracting it from every question (the location-shift model of
    section 9 point 4).
    """

    def __init__(self, d: Sequence[float], documents: Sequence[str], signs: np.ndarray) -> None:
        """Hold document sums and sizes and the per-draw sums the test needs.

        Args:
            d: Per-question contrast scores.
            documents: Document ID per question.
            signs: Draws by documents matrix of +1 and -1.
        """
        if len(documents) != len(d):
            raise ValueError("need one document ID per score")
        names = sorted(set(documents))
        index = {name: j for j, name in enumerate(names)}
        sums = np.zeros(len(names))
        sizes = np.zeros(len(names))
        for value, name in zip(d, documents, strict=True):
            sums[index[name]] += value
            sizes[index[name]] += 1
        self.n = len(d)
        self.n_draws = len(signs)
        self.estimate = math.fsum(d) / self.n
        self._sums = sums
        self._sizes = sizes
        self._signed_sums = signs @ sums
        self._signed_sizes = signs @ sizes

    def p_value(self, shift: float) -> float:
        """Return the sign-flip p-value for the null "true shift equals ``shift``".

        Args:
            shift: The shift tested; 0 gives the decision p-value.

        Returns:
            (1 + draws at least as large) / (draws + 1).
        """
        observed = float(np.sum(self._sums - shift * self._sizes)) / self.n
        draws = (self._signed_sums - shift * self._signed_sizes) / self.n
        return (1 + count_at_least(observed, draws)) / (self.n_draws + 1)

    def _end(self, direction: int, alpha: float, precision: float) -> float:
        inner = self.estimate
        step = 1.0
        while self.p_value(inner + direction * step) >= alpha:
            step *= 2
            if step > _MAX_SHIFT:
                return direction * math.inf
        outer = inner + direction * step
        while abs(outer - inner) > precision:
            middle = (inner + outer) / 2
            if self.p_value(middle) < alpha:
                outer = middle
            else:
                inner = middle
        return inner

    def interval(self, alpha: float = 0.05, precision: float = 1e-4) -> tuple[float, float]:
        """Return the lowest and highest shift not rejected at ``alpha``.

        Each end is found by bisection to ``precision`` and is the bracket end
        that is not rejected. "Rejected" means p below ``alpha``, the same rule
        that makes a row count (section 7).

        Args:
            alpha: Test level.
            precision: Bisection width.

        Returns:
            The lower and upper ends.
        """
        return self._end(-1, alpha, precision), self._end(1, alpha, precision)


@dataclass(frozen=True)
class SignFlipResult:
    """One FinanceBench sign-flip test.

    Attributes:
        estimate: Question-weighted mean of ``d``.
        p_value: Two-sided p-value.
        ci_low: Lowest shift not rejected at 0.05.
        ci_high: Highest shift not rejected at 0.05.
        n: Number of questions.
        n_documents: Number of documents.
        n_draws: Number of sign draws.
        seed: Seed of the draws (numpy ``default_rng``).
    """

    estimate: float
    p_value: float
    ci_low: float
    ci_high: float
    n: int
    n_documents: int
    n_draws: int
    seed: int


def sign_flip_test(
    d: Sequence[float],
    documents: Sequence[str],
    *,
    n_draws: int = SIGN_FLIP_DRAWS,
    seed: int = SIGN_FLIP_SEED,
) -> SignFlipResult:
    """Run the document-level sign-flip test and invert it for the 95% interval.

    The draws come from ``numpy.random.default_rng(seed)``: one row of +1 or -1
    per draw, one column per document in sorted ID order. The p-value and the
    interval use the same draws.

    Args:
        d: Per-question contrast scores.
        documents: Document ID per question.
        n_draws: Number of sign draws (100,000 registered).
        seed: Seed of the draws (20261101 registered).

    Returns:
        The test result.
    """
    n_documents = len(set(documents))
    rng = np.random.default_rng(seed)
    # The registered call (default integer type); another dtype draws another stream.
    signs = rng.integers(0, 2, size=(n_draws, n_documents)) * 2 - 1
    flip = SignFlip(d, documents, signs)
    low, high = flip.interval()
    return SignFlipResult(
        estimate=flip.estimate,
        p_value=flip.p_value(0.0),
        ci_low=low,
        ci_high=high,
        n=len(d),
        n_documents=n_documents,
        n_draws=n_draws,
        seed=seed,
    )
