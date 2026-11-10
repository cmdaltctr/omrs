"""Determinism check for repeated retrieval runs (Experiment 35, task 2.8).

Retrieval with the same index, query and settings must return the same
ranked list on every run. This module compares the lists of repeated runs
per question and reports every difference with its size: how many
questions differ, and for each question the first rank where the lists
part ways.

Pure standard library.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["DeterminismReport", "QuestionMismatch", "compare_runs"]


@dataclass(frozen=True)
class QuestionMismatch:
    """One question whose retrieved lists differ between runs.

    Attributes:
        question_id: The question identifier.
        first_differing_rank: The lowest 1-based rank where any run differs
            from the reference run. A list that is shorter or longer differs
            at the first rank the shorter list lacks. ``None`` when the only
            difference is a run that lacks the question.
        differing_runs: Runs whose list differs from the reference run.
        missing_in_runs: Runs that have no list for this question.
    """

    question_id: str
    first_differing_rank: int | None
    differing_runs: tuple[Hashable, ...]
    missing_in_runs: tuple[Hashable, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the mismatch as plain data for a JSON record."""
        return {
            "question_id": self.question_id,
            "first_differing_rank": self.first_differing_rank,
            "differing_runs": list(self.differing_runs),
            "missing_in_runs": list(self.missing_in_runs),
        }


@dataclass(frozen=True)
class DeterminismReport:
    """Outcome of comparing the retrieved lists of repeated runs.

    Attributes:
        questions_compared: Number of distinct questions seen in any run.
        mismatches: One entry per differing question, in question order.
    """

    questions_compared: int
    mismatches: list[QuestionMismatch] = field(default_factory=list)

    @property
    def n_differing(self) -> int:
        """Number of questions that differ between runs."""
        return len(self.mismatches)

    @property
    def ok(self) -> bool:
        """True when every run returned identical lists for every question."""
        return not self.mismatches

    def to_dict(self) -> dict[str, Any]:
        """Return the report as plain data for a JSON record."""
        return {
            "ok": self.ok,
            "questions_compared": self.questions_compared,
            "questions_differing": self.n_differing,
            "mismatches": [m.to_dict() for m in self.mismatches],
        }


def _first_differing_rank(reference: Sequence[str], other: Sequence[str]) -> int:
    """Return the 1-based rank where two different lists first part ways."""
    for rank, (left, right) in enumerate(zip(reference, other, strict=False), start=1):
        if left != right:
            return rank
    return min(len(reference), len(other)) + 1


def compare_runs(runs: Mapping[Hashable, Mapping[str, Sequence[str]]]) -> DeterminismReport:
    """Compare the retrieved lists of repeated runs, question by question.

    For each question the reference is the first run, in the order given,
    that has a list for it. Every other run is compared with that list.

    Args:
        runs: Run label (for example 1, 2, 3) to a mapping of question id to
            the ranked list of retrieved ids.

    Returns:
        A report with the number of questions compared and one mismatch per
        question that differs.

    Raises:
        ValueError: When fewer than two runs are given.
    """
    if len(runs) < 2:
        raise ValueError(f"need at least two runs to compare, got {len(runs)}")

    question_ids = sorted({question for run in runs.values() for question in run})
    mismatches: list[QuestionMismatch] = []
    for question in question_ids:
        present = [(label, run[question]) for label, run in runs.items() if question in run]
        missing = tuple(label for label, run in runs.items() if question not in run)
        _, reference = present[0]
        differing = [
            (label, _first_differing_rank(reference, ranked))
            for label, ranked in present[1:]
            if list(ranked) != list(reference)
        ]
        if not differing and not missing:
            continue
        mismatches.append(
            QuestionMismatch(
                question_id=question,
                first_differing_rank=min((rank for _, rank in differing), default=None),
                differing_runs=tuple(label for label, _ in differing),
                missing_in_runs=missing,
            )
        )
    return DeterminismReport(questions_compared=len(question_ids), mismatches=mismatches)
