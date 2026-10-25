"""Reserved experiment numbers in ``reserved.json`` (design D7).

A reservation keeps a number for an experiment that has no folder yet, for
example one planned in an OpenSpec change, a NiftyPM task or another
branch. The file is tracked in git, so a reservation made in one worktree
reaches the others on merge. The folder creator never uses a reserved number.

File shape::

    {
      "format": "omrs-experiment-reservations/1",
      "reservations": [{"number": "35", "reason": "...", "ref": "..."}]
    }
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .record import (
    ONE_LINE_PATTERN,
    RecordError,
    check_format,
    describe_validation_error,
    read_json,
)

RESERVATIONS_FORMAT = "omrs-experiment-reservations/1"
"""The format string a version 1 reservations file declares."""

RESERVED_FILE = "reserved.json"
"""The reservations file name inside the experiments directory."""

_RESERVED_NUMBER_PATTERN = r"^[0-9]+(?:[a-z]|\.[0-9]+)?$"


class Reservation(BaseModel):
    """One reserved number with the reason and a reference to where it is planned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: str = Field(pattern=_RESERVED_NUMBER_PATTERN)
    reason: str = Field(min_length=1, pattern=ONE_LINE_PATTERN)
    ref: str = Field(min_length=1, pattern=ONE_LINE_PATTERN)


class ReservationsFile(BaseModel):
    """The whole ``reserved.json`` file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str
    reservations: tuple[Reservation, ...] = ()

    @model_validator(mode="after")
    def _numbers_are_unique(self) -> ReservationsFile:
        seen: set[str] = set()
        for entry in self.reservations:
            if entry.number in seen:
                raise ValueError(f"number {entry.number} is reserved more than once")
            seen.add(entry.number)
        return self


def load_reservations(root: Path) -> tuple[Reservation, ...]:
    """Read ``reserved.json`` from the experiments directory.

    Args:
        root: The experiments directory.

    Returns:
        The reservations in file order. A missing file means no reservations.

    Raises:
        UnsupportedFormatError: The file declares another format version.
        RecordError: The file is not JSON or breaks a rule. The message names the key.
    """
    path = root / RESERVED_FILE
    if not path.exists():
        return ()
    data = read_json(path)
    check_format(data, RESERVATIONS_FORMAT)
    try:
        return ReservationsFile.model_validate(data).reservations
    except ValidationError as exc:
        raise RecordError(f"{RESERVED_FILE}: {describe_validation_error(exc)}") from None
