"""The local OCR backend contract (change local-ocr-backends, design D7).

A backend reads pages and reports what it read. It never decides escalation: the
shared rule in ``chain`` does, with the backend's registered facts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendPage:
    """One page a backend read.

    Attributes:
        page: 1-based page number.
        text: The page text, possibly empty.
        confidence: One number in [0, 1], or ``None`` when the backend gave none.
        model: The model identity (``name@revision``), or ``None``.
        hosted_recommended: Whether the backend recommends a hosted engine.
    """

    page: int
    text: str
    confidence: float | None
    model: str | None
    hosted_recommended: bool = False


class LocalOcrBackend(Protocol):
    """What one local OCR backend has."""

    def read_pages(self, file: Path, pages: list[int], *, settings: Any) -> list[BackendPage]:
        """Read *pages* (1-based) of *file*. A page not returned counts as missing.

        Raises:
            Exception: On a runtime failure; ``ImportError`` when not installed.
        """
        ...

    def identity(self, settings: Any) -> str | None:
        """Return the model identity (``name@revision``), or ``None``."""
        ...


@dataclass(frozen=True)
class LocalOcrPage:
    """One page after the local tier, with its escalation verdict.

    Attributes:
        page: 1-based page number.
        text: The kept text. For an escalated page, the text of the first listed
            backend that returned non-empty text, else empty.
        confidence: The confidence the backend of ``text`` reported, or ``None``.
        model: The model identity of that backend's read, or ``None``.
        escalates: Whether the page goes to the OCR engine list.
        reasons: The escalation reasons of the last backend that read the page.
        producer: The ``ocr_backend`` value of the backend whose text is kept, or
            ``None`` when no backend returned text.
    """

    page: int
    text: str
    confidence: float | None
    model: str | None
    escalates: bool
    reasons: tuple[str, ...]
    producer: str | None = None


def _characters(text: str) -> int:
    return len("".join(text.split()))


def page_confidence(lines: Iterable[tuple[str, float]]) -> float | None:
    """Reduce line confidences to one page confidence.

    The rule Experiment 46 used: the mean of the line confidences, weighted by
    the number of characters (whitespace excluded) in each line.

    Args:
        lines: ``(text, confidence)`` per line.

    Returns:
        The weighted mean, or ``None`` when the lines hold no character.
    """
    weighted = [(_characters(text), confidence) for text, confidence in lines]
    total = sum(count for count, _ in weighted)
    if not total:
        return None
    return sum(count * confidence for count, confidence in weighted) / total
