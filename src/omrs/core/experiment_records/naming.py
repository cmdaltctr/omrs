"""Folder names, slugs and the natural number order (design D5).

A folder is named ``<number>-<slug>-<YYYY-MM-DD>``. The folder name is the
experiment's identity; the number is a label that old folders sometimes
repeat. An unnumbered folder (``<slug>-<YYYY-MM-DD>``, slug starting with a
letter) is valid only when it carries a record.

Numbers sort naturally: ``5 < 5b < 6 < 10 < 10.1 < 10b``. Unnumbered folders
come last, by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date  # noqa: N812 - the field is named ``date``

_NUMBER = r"[0-9]+(?:[a-z]|\.[0-9]+)?"
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
# An unnumbered slug starts with a letter, so ``22-<date>`` is never read as one.
_UNNUMBERED_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"

NUMBER_RE = re.compile(rf"(?:{_NUMBER})?")
SLUG_RE = re.compile(_SLUG)
NUMBERED_FOLDER_RE = re.compile(rf"(?P<number>{_NUMBER})-(?P<slug>{_SLUG})-(?P<date>{_DATE})")
UNNUMBERED_FOLDER_RE = re.compile(rf"(?P<slug>{_UNNUMBERED_SLUG})-(?P<date>{_DATE})")
_NUMBER_PARTS_RE = re.compile(r"(?P<whole>[0-9]+)(?:(?P<letter>[a-z])|\.(?P<dotted>[0-9]+))?")


@dataclass(frozen=True)
class FolderName:
    """The parts of a folder name. ``number`` is empty for an unnumbered folder."""

    number: str
    slug: str
    date: Date


def is_valid_number(number: str) -> bool:
    """Return True for ``22``, ``5b``, ``10.1`` or the empty string."""
    return NUMBER_RE.fullmatch(number) is not None


def is_valid_slug(slug: str) -> bool:
    """Return True when *slug* is lower-case letters and digits joined by single hyphens."""
    return SLUG_RE.fullmatch(slug) is not None


def _parse_date(text: str) -> Date | None:
    try:
        return Date.fromisoformat(text)
    except ValueError:
        return None


def parse_folder_name(name: str) -> FolderName | None:
    """Split a folder name into number, slug and date.

    Args:
        name: The folder name.

    Returns:
        The parts, or None when the name follows neither the numbered nor
        the unnumbered pattern, or when the date is not a real day.
    """
    match = NUMBERED_FOLDER_RE.fullmatch(name)
    number = match.group("number") if match else ""
    if match is None:
        match = UNNUMBERED_FOLDER_RE.fullmatch(name)
    if match is None:
        return None
    day = _parse_date(match.group("date"))
    if day is None:
        return None
    return FolderName(number=number, slug=match.group("slug"), date=day)


def folder_name(number: str, slug: str, day: Date) -> str:
    """Build ``<number>-<slug>-<YYYY-MM-DD>``.

    Raises:
        ValueError: The number or the slug breaks the naming rules.
    """
    if not number or not is_valid_number(number):
        raise ValueError(f"number {number!r} must be digits, optionally with a letter or .digits")
    if not is_valid_slug(slug):
        raise ValueError(
            f"slug {slug!r} must be lower-case letters and digits joined by single hyphens"
        )
    return f"{number}-{slug}-{day.isoformat()}"


def whole_number(number: str) -> int | None:
    """Return the leading whole number (``10`` for ``10.1`` and ``10b``), or None."""
    match = _NUMBER_PARTS_RE.fullmatch(number)
    return int(match.group("whole")) if match else None


def number_key(number: str) -> tuple[int, int, int, str]:
    """Return a sort key that orders ``5 < 5b < 6 < 10 < 10.1 < 10b``.

    Raises:
        ValueError: *number* is empty or not a valid number.
    """
    match = _NUMBER_PARTS_RE.fullmatch(number)
    if match is None:
        raise ValueError(f"{number!r} is not an experiment number")
    whole = int(match.group("whole"))
    if match.group("dotted") is not None:
        return (whole, 1, int(match.group("dotted")), "")
    if match.group("letter") is not None:
        return (whole, 2, 0, match.group("letter"))
    return (whole, 0, 0, "")


def folder_sort_key(number: str, folder: str) -> tuple[int, tuple[int, int, int, str], str]:
    """Sort key: by number, then folder name; unnumbered folders last, by name."""
    if number and _NUMBER_PARTS_RE.fullmatch(number):
        return (0, number_key(number), folder)
    return (1, (0, 0, 0, ""), folder)
