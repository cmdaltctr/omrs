"""Create a new experiment folder from the packaged templates (spec "New experiment folders").

The new folder is ``<number>-<slug>-<YYYY-MM-DD>``. It holds an
``experiment.json`` record at status ``PLANNED`` and the template files the
size needs. The number is the next free whole number, or the next free
letter for a follow-up (``38a``, ``38b``). Reserved numbers are never used.
The creator never overwrites or changes an existing file or folder.
"""

from __future__ import annotations

import re
import shutil
import string
from collections.abc import Sequence
from datetime import date as Date  # noqa: N812 - matches the record field name
from pathlib import Path

from pydantic import ValidationError

from .naming import folder_name, is_valid_slug, whole_number
from .record import (
    FORMAT,
    RECORD_FILE,
    Category,
    ExperimentRecord,
    Refs,
    Size,
    Status,
    describe_validation_error,
    dump_record,
)
from .reserved import Reservation, load_reservations
from .scan import ExperimentFolder, scan_experiments
from .templates import read_template

# Output file name -> template file name, per size.
_QUICK_FILES = {"report.md": "report-quick.md"}
_PLANNED_FILES = {"protocol.md": "protocol.md", "plan.json": "plan.json", "report.md": "report.md"}
FILES_BY_SIZE: dict[Size, dict[str, str]] = {
    Size.QUICK: _QUICK_FILES,
    Size.STANDARD: _PLANNED_FILES,
    Size.CONFIRMATORY: _PLANNED_FILES,
}

_FOLDER_PLACEHOLDER = "<number>-<slug>-<YYYY-MM-DD>"


class ScaffoldError(ValueError):
    """A new experiment folder cannot be created. Nothing was written."""


def _taken(folders: Sequence[ExperimentFolder], reservations: Sequence[Reservation]) -> set[str]:
    return {folder.number for folder in folders if folder.number} | {
        entry.number for entry in reservations
    }


def next_number(folders: Sequence[ExperimentFolder], reservations: Sequence[Reservation]) -> str:
    """Return the next free whole number after the highest folder number.

    Args:
        folders: The detected folders.
        reservations: The reserved numbers. They are skipped.

    Returns:
        The number as a string, for example ``"43"``.
    """
    wholes = [whole_number(folder.number) for folder in folders]
    candidate = max((value for value in wholes if value is not None), default=0) + 1
    taken = _taken(folders, reservations)
    while str(candidate) in taken:
        candidate += 1
    return str(candidate)


def follow_up_number(
    base: str, folders: Sequence[ExperimentFolder], reservations: Sequence[Reservation]
) -> str:
    """Return the next free follow-up number for experiment *base* (``38a``, then ``38b``).

    Raises:
        ScaffoldError: *base* is not a plain number, no folder uses it, or
            every letter is taken.
    """
    if not re.fullmatch(r"[0-9]+", base):
        raise ScaffoldError(f"a follow-up needs a plain number such as 38, not {base!r}")
    if not any(folder.number == base for folder in folders):
        raise ScaffoldError(f"no experiment folder uses number {base}")
    taken = _taken(folders, reservations)
    for letter in string.ascii_lowercase:
        if f"{base}{letter}" not in taken:
            return f"{base}{letter}"
    raise ScaffoldError(f"every follow-up letter of experiment {base} is taken")


def _fill(text: str, *, name: str, number: str, title: str | None) -> str:
    text = text.replace(_FOLDER_PLACEHOLDER, name).replace("<number>", number)
    return text.replace("<title>", title) if title is not None else text


def create_experiment(
    root: Path,
    *,
    slug: str,
    title: str,
    category: Category,
    size: Size,
    day: Date,
    follow_up: str | None = None,
) -> Path:
    """Create a new experiment folder with its record and template files.

    Args:
        root: The experiments directory.
        slug: Lower-case letters and digits joined by single hyphens.
        title: The one-line title for the record and the index.
        category: The experiment category.
        size: The experiment size. It decides the template files.
        day: The planning date, used in the folder name and the record.
        follow_up: A plain experiment number. When given, the new folder
            takes that number's next free letter.

    Returns:
        The new folder path.

    Raises:
        ScaffoldError: A rule fails or the folder name already exists.
            Nothing is written.
        OSError: A file cannot be written. The new folder is removed first.
    """
    if not root.is_dir():
        raise ScaffoldError(f"{root} is not a directory")
    if not is_valid_slug(slug):
        raise ScaffoldError(
            f"slug {slug!r} must be lower-case letters and digits joined by single hyphens"
        )
    folders = scan_experiments(root)
    reservations = load_reservations(root)
    if follow_up is None:
        number = next_number(folders, reservations)
    else:
        number = follow_up_number(follow_up, folders, reservations)
    name = folder_name(number, slug, day)
    try:
        record = ExperimentRecord(
            format=FORMAT,
            number=number,
            title=title,
            date=day,
            category=category,
            size=size,
            status=Status.PLANNED,
            superseded_by=None,
            finding="",
            refs=Refs(),
        )
    except ValidationError as exc:
        raise ScaffoldError(f"the record is not valid: {describe_validation_error(exc)}") from None
    files = {RECORD_FILE: dump_record(record)}
    for target, template in FILES_BY_SIZE[size].items():
        # A title is free text, so it goes into Markdown only, never into JSON.
        text_title = title if target.endswith(".md") else None
        files[target] = _fill(read_template(template), name=name, number=number, title=text_title)
    folder = root / name
    try:
        folder.mkdir()
    except FileExistsError:
        raise ScaffoldError(f"{name} already exists in {root}") from None
    try:
        for target, text in files.items():
            with (folder / target).open("x", encoding="utf-8") as handle:
                handle.write(text)
    except BaseException:
        # Remove only the folder this call created, so no half-made experiment stays.
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder
