"""Uncited prose segments of a saved answer (task 16.29; pre-registration section 6).

An uncited segment is a prose segment with no valid ordinal that OMRS's
``split_claims`` drops: it is not a claim and no checker sees it. This module
walks the answer the same way ``split_claims`` does (its prose segmenter,
ordinal parser and marker cleaning), so a trailing marker such as ``"Text.
[1]"`` still makes ``Text.`` a claim and not an uncited segment.
"""

from __future__ import annotations

import re

from omrs.core.answer.citations import parse_citation_ordinals
from omrs.core.answer.verify import _ORDINAL_MARKER, _prose_segments, split_claims


def _clean(segment: str) -> str:
    text = _ORDINAL_MARKER.sub("", segment)
    return re.sub(r"\s+([.,;:!?])", r"\1", " ".join(text.split())).strip()


def uncited_segments(text: str, evidence_count: int) -> list[str]:
    """Return the prose segments of *text* that carry no valid ordinal and become no claim.

    Args:
        text: The saved answer text.
        evidence_count: The number of evidence items (highest valid ordinal).

    Returns:
        The cleaned segment texts, in answer order.
    """
    found: list[str] = []
    pending = False  # the last candidate a trailing marker can still attach to is uncited
    for segment in _prose_segments(text or ""):
        if segment is None:
            pending = False
            continue
        stripped = segment.strip()
        if not stripped:
            continue
        ordinals = parse_citation_ordinals(stripped, evidence_count)
        cleaned = _clean(stripped)
        if not ordinals:
            if cleaned:
                found.append(cleaned)
                pending = True
            continue
        if not cleaned and pending:
            found.pop()
        pending = False
    return found


def segment_counts(text: str, evidence_count: int) -> tuple[int, int]:
    """Return the prose segments of an answer (claims plus uncited) and the uncited count."""
    uncited = len(uncited_segments(text, evidence_count))
    return len(split_claims(text or "", evidence_count)) + uncited, uncited
