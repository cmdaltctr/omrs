"""Experiment 35 uncited segments (task 16.29): the segments ``split_claims`` drops."""

from __future__ import annotations

import pytest
from tests._exp35_fixtures import load

segments35 = load("segments35")


@pytest.mark.parametrize(
    ("text", "uncited", "counts"),
    [
        ("Fact one [1]. Uncited fact.", ["Uncited fact."], (2, 1)),
        ("Text. [1]", [], (1, 0)),
        ("A. B [1]. [2]", ["A."], (2, 1)),
        ("A. C. [1]", ["A."], (2, 1)),
        ("# Heading\n\nA [1].\n\nB.", ["B."], (2, 1)),
        ("Out of range [9].", ["Out of range."], (1, 1)),
        ("", [], (0, 0)),
    ],
)
def test_uncited_segments_follow_split_claims(text: str, uncited: list[str], counts: tuple) -> None:
    assert segments35.uncited_segments(text, 2) == uncited
    assert segments35.segment_counts(text, 2) == counts
