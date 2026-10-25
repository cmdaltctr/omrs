"""The experiment record model, format ``omrs-experiment/1`` (design D2 to D4).

``experiment.json`` holds the facts that change after planning or that the
index needs. The pydantic model is the single source of the rules. The
shipped JSON Schema is generated from it (:func:`schema_text`), and a test
fails when the file and the model differ.

Readers refuse an unknown format version instead of ignoring it, so an old
release never drops a field that a newer release wrote.
"""

from __future__ import annotations

import json
from datetime import date as Date  # noqa: N812 - the field is named ``date``
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

FORMAT = "omrs-experiment/1"
"""The format string every version 1 record declares."""

RECORD_FILE = "experiment.json"
"""The record file name inside an experiment folder."""

NUMBER_PATTERN = r"^(?:[0-9]+(?:[a-z]|\.[0-9]+)?)?$"
"""Digits, then one optional lower-case letter or dot-and-digits. Empty means unnumbered."""

ONE_LINE_PATTERN = r"^[^\r\n]*$"
FOLDER_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class RecordError(ValueError):
    """An experiment record, or a file in the same format family, is not valid."""


class UnsupportedFormatError(RecordError):
    """A file declares a format version this release does not know.

    Attributes:
        version: The format string the file declares.
    """

    def __init__(self, version: str, expected: str = FORMAT) -> None:
        self.version = version
        family, _, known = expected.rpartition("/")
        prefix, _, declared = version.rpartition("/")
        newer = prefix == family and declared.isascii() and declared.isdigit()
        if newer and int(declared) > int(known):
            message = (
                f"the file declares format {version!r}, which needs a newer omrs. "
                f"This release reads only {expected!r}."
            )
        else:
            message = f"the format value {version!r} is not recognised; expected {expected!r}"
        super().__init__(message)


class Status(StrEnum):
    """The seven experiment status values."""

    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    PASS = "PASS"  # noqa: S105 - a status word, not a password
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    MEASURED = "MEASURED"
    SUPERSEDED = "SUPERSEDED"


class Category(StrEnum):
    """The area of the system an experiment tests."""

    RETRIEVAL = "retrieval"
    INGESTION = "ingestion"
    RUNTIME = "runtime"
    GENERATION = "generation"
    GRAPH = "graph"
    REVIEW = "review"


class Size(StrEnum):
    """How much planning an experiment carries. The size decides the files it needs."""

    QUICK = "Quick"
    STANDARD = "Standard"
    CONFIRMATORY = "Confirmatory"


_FROZEN = ConfigDict(extra="forbid", frozen=True)


class Refs(BaseModel):
    """Links to decision records, OpenSpec changes and tasks, without free text."""

    model_config = _FROZEN

    adrs: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()


class MigrationNote(BaseModel):
    """How a converted record was made, so the conversion can be checked and reversed."""

    model_config = _FROZEN

    from_status: str = Field(pattern=ONE_LINE_PATTERN)
    source: str = Field(min_length=1, pattern=ONE_LINE_PATTERN)
    date: Date


# Rules the model validator applies, written in JSON Schema so editors and
# other languages enforce them too.
_CROSS_FIELD_SCHEMA: dict[str, Any] = {
    "allOf": [
        {
            "if": {"properties": {"status": {"const": "SUPERSEDED"}}},
            "then": {
                "properties": {"superseded_by": {"type": "string"}},
                "required": ["superseded_by"],
            },
            "else": {"properties": {"superseded_by": {"type": "null"}}},
        },
        {
            "if": {"properties": {"migration": {"type": "null"}}},
            "then": {
                "properties": {"category": {"type": "string"}, "size": {"type": "string"}},
                "required": ["category", "size"],
            },
        },
    ]
}


class ExperimentRecord(BaseModel):
    """One experiment's record, stored as ``experiment.json`` in its folder."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="omrs experiment record",
        json_schema_extra=_CROSS_FIELD_SCHEMA,
    )

    format: Literal["omrs-experiment/1"]
    number: str = Field(pattern=NUMBER_PATTERN)
    title: str = Field(min_length=1, pattern=ONE_LINE_PATTERN)
    date: Date
    category: Category | None = None
    size: Size | None = None
    status: Status
    superseded_by: str | None = Field(default=None, pattern=FOLDER_REF_PATTERN)
    finding: str = Field(pattern=ONE_LINE_PATTERN)
    refs: Refs | None = None
    migration: MigrationNote | None = None

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ExperimentRecord:
        if self.status is Status.SUPERSEDED and not self.superseded_by:
            raise ValueError(
                "status SUPERSEDED needs superseded_by: name the folder that replaces it"
            )
        if self.status is not Status.SUPERSEDED and self.superseded_by is not None:
            raise ValueError(
                f"superseded_by is set but status is {self.status.value}; "
                "only a SUPERSEDED record names a superseding folder"
            )
        if self.migration is None:
            missing = [name for name in ("category", "size") if getattr(self, name) is None]
            if missing:
                raise ValueError(
                    f"{' and '.join(missing)} must be set unless the record has a migration note"
                )
        return self


def describe_validation_error(exc: ValidationError) -> str:
    """Return a one-line message that names each failing key.

    Args:
        exc: The pydantic error.

    Returns:
        ``key: message`` parts joined with ``; ``.
    """
    parts = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"])
        message = str(error["msg"]).removeprefix("Value error, ")
        parts.append(f"{where}: {message}" if where else message)
    return "; ".join(parts)


def check_format(data: object, expected: str) -> None:
    """Refuse *data* unless it is an object that declares *expected* as its format.

    Args:
        data: The decoded JSON value.
        expected: The format string this reader knows.

    Raises:
        RecordError: *data* is not an object or has no format string.
        UnsupportedFormatError: *data* declares another format.
    """
    if not isinstance(data, dict):
        raise RecordError(f"the file must hold a JSON object that declares {expected!r}")
    version = data.get("format")
    if version is None:
        raise RecordError(f"format: the key is missing; expected {expected!r}")
    if not isinstance(version, str):
        raise RecordError(f"format: must be the string {expected!r}")
    if version != expected:
        raise UnsupportedFormatError(version, expected)


def parse_record(data: object) -> ExperimentRecord:
    """Validate decoded JSON as a version 1 record.

    Args:
        data: The value from ``json.loads``.

    Returns:
        The record.

    Raises:
        UnsupportedFormatError: The format version is not ``omrs-experiment/1``.
        RecordError: Any other rule fails. The message names the key.
    """
    check_format(data, FORMAT)
    try:
        return ExperimentRecord.model_validate(data)
    except ValidationError as exc:
        raise RecordError(describe_validation_error(exc)) from None


def read_json(path: Path) -> object:
    """Read a UTF-8 JSON file.

    Raises:
        RecordError: The file cannot be read or is not valid JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecordError(f"cannot read {path.name}: {exc.strerror or exc}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordError(f"{path.name} is not valid JSON: {exc}") from None


def load_record(path: Path) -> ExperimentRecord:
    """Read and validate an ``experiment.json`` file.

    Args:
        path: The record file.

    Returns:
        The record.

    Raises:
        RecordError: The file is missing, is not JSON, or breaks a rule.
    """
    return parse_record(read_json(path))


def dump_record(record: ExperimentRecord) -> str:
    """Return the record as JSON text in field order, with a final newline.

    ``refs`` and ``migration`` are left out when they are not set. Every
    other key is written, so the file shows each field.
    """
    exclude = {name for name in ("refs", "migration") if getattr(record, name) is None}
    data = record.model_dump(mode="json", exclude=exclude)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def schema_text() -> str:
    """Return the JSON Schema for the record, with sorted keys and a final newline."""
    return json.dumps(ExperimentRecord.model_json_schema(), indent=2, sort_keys=True) + "\n"
