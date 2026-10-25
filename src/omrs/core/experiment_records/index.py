"""The generated index block in ``EXP_README.md`` (design D6).

The block sits between two marker lines. It holds the experiment table
(``#``, ``Experiment``, ``Date``, ``Status``, ``Key Finding / Purpose``) and,
when numbers are reserved, a ``### Reserved numbers`` table (``#``,
``Reason``, ``Reference``), so a planned experiment without a folder stays
visible. Cells are not padded, so a new row changes one line. A ``|`` in a
cell becomes ``\\|``. Every byte outside the markers is kept.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from .naming import folder_sort_key, number_key
from .reserved import Reservation
from .scan import ExperimentFolder

INDEX_START = "<!-- omrs:experiment-index:start -->"
INDEX_END = "<!-- omrs:experiment-index:end -->"
README_FILE = "EXP_README.md"

_EXPERIMENT_HEADER = (
    "| # | Experiment | Date | Status | Key Finding / Purpose |\n|---|---|---|---|---|\n"
)
_RESERVED_HEADER = "### Reserved numbers\n\n| # | Reason | Reference |\n|---|---|---|\n"


class IndexFileError(ValueError):
    """``EXP_README.md`` cannot be used as the index file."""


class IndexMarkerError(IndexFileError):
    """``EXP_README.md`` lacks a marker line, repeats one, or has them in the wrong order."""


def _cell(text: str) -> str:
    # Double only a backslash that a pipe follows, so ``a\|b`` cannot end the cell
    # early. Other backslashes stay as written: inside a code span they show literally.
    return text.replace("\\|", "\\\\|").replace("|", "\\|")


def _link_text(title: str) -> str:
    return _cell(title).replace("[", "\\[").replace("]", "\\]")


def _link_target(name: str) -> str:
    target = f"./{name}/"
    # A space or a parenthesis ends a plain link target; angle brackets keep it whole.
    return f"<{target}>" if any(char in name for char in " ()") else target


def render_index(folders: Iterable[ExperimentFolder], reservations: Iterable[Reservation]) -> str:
    """Render the block that goes between the markers.

    Args:
        folders: The detected folders. Folders without a valid record are
            left out; the checker reports them.
        reservations: The reserved numbers. With none, the reserved-numbers
            heading and table are left out.

    Returns:
        The block text, ending with a newline. Rows are ordered by number,
        then folder name, with unnumbered experiments last. Reservations
        are in natural number order.
    """
    entries = sorted(
        ((folder.name, folder.record) for folder in folders if folder.record is not None),
        key=lambda entry: folder_sort_key(entry[1].number, entry[0]),
    )
    lines = [_EXPERIMENT_HEADER]
    for name, record in entries:
        cells = (
            _cell(record.number),
            f"[{_link_text(record.title)}]({_link_target(name)})",
            record.date.isoformat(),
            record.status.value,
            _cell(record.finding),
        )
        lines.append("| " + " | ".join(cells) + " |\n")
    reserved = sorted(reservations, key=lambda entry: number_key(entry.number))
    if reserved:
        lines.append("\n" + _RESERVED_HEADER)
        for entry in reserved:
            cells = (_cell(entry.number), _cell(entry.reason), _cell(entry.ref))
            lines.append("| " + " | ".join(cells) + " |\n")
    return "".join(lines)


def _marker_lines(lines: Sequence[str]) -> tuple[int, int]:
    found: dict[str, list[int]] = {INDEX_START: [], INDEX_END: []}
    for position, line in enumerate(lines):
        if line.strip() in found:
            found[line.strip()].append(position)
    for marker, positions in found.items():
        if not positions:
            raise IndexMarkerError(f"{README_FILE} has no marker line {marker}")
        if len(positions) > 1:
            raise IndexMarkerError(f"{README_FILE} has the marker {marker} more than once")
    start, end = found[INDEX_START][0], found[INDEX_END][0]
    if end < start:
        raise IndexMarkerError(f"{README_FILE} has {INDEX_END} before {INDEX_START}")
    return start, end


def read_block(text: str) -> str:
    """Return the text between the marker lines.

    Raises:
        IndexMarkerError: A marker is missing, repeated or out of order.
    """
    lines = text.splitlines(keepends=True)
    start, end = _marker_lines(lines)
    return "".join(lines[start + 1 : end])


def replace_block(text: str, block: str) -> str:
    """Return *text* with the lines between the markers replaced by *block*.

    The marker lines and everything outside them are kept byte for byte.

    Raises:
        IndexMarkerError: A marker is missing, repeated or out of order.
    """
    lines = text.splitlines(keepends=True)
    start, end = _marker_lines(lines)
    return "".join(lines[: start + 1]) + block + "".join(lines[end:])


def index_is_current(
    text: str, folders: Iterable[ExperimentFolder], reservations: Iterable[Reservation]
) -> bool:
    """Return True when the block in *text* equals the generated block.

    Raises:
        IndexMarkerError: A marker is missing, repeated or out of order.
    """
    return read_block(text) == render_index(folders, reservations)


def read_readme(readme: Path) -> str:
    """Read ``EXP_README.md`` as UTF-8 text, keeping its line endings.

    Raises:
        IndexFileError: The file is not valid UTF-8.
        OSError: The file cannot be read.
    """
    try:
        return readme.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IndexFileError(f"{readme.name} is not valid UTF-8: {exc.reason}") from None


def write_index(
    readme: Path, folders: Iterable[ExperimentFolder], reservations: Iterable[Reservation]
) -> bool:
    """Replace the marked block in *readme* with the generated block.

    The file is replaced atomically. When a marker is missing, nothing is
    written.

    Args:
        readme: The ``EXP_README.md`` path.
        folders: The detected folders.
        reservations: The reserved numbers.

    Returns:
        True when the file changed, False when it was already current.

    Raises:
        IndexMarkerError: A marker is missing, repeated or out of order.
        IndexFileError: The file is not valid UTF-8.
        OSError: The file cannot be read or written.
    """
    text = read_readme(readme)
    new = replace_block(text, render_index(folders, reservations))
    if new == text:
        return False
    temporary = readme.with_name(f".{readme.name}.tmp")
    temporary.write_bytes(new.encode("utf-8"))
    os.replace(temporary, readme)
    return True
