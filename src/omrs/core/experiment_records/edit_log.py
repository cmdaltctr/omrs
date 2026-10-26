"""Edit records in ``edits.jsonl`` (edit-experiment-files-in-library, D2 and D3).

Each save of ``protocol.md`` or the report from the web app appends one JSON
line to ``edits.jsonl`` in the experiment folder. Git tracks the file, so a
reader can match each line against the history of the edited file. Writers
only append; no tool changes or removes an earlier line. A line holds no
user name, login or path, because the file goes into git.

``experiment.json`` never changes for an edit. Older readers do not look at
this file, so an edited folder stays valid for them.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .record import ONE_LINE_PATTERN, RecordError, Status, check_format, describe_validation_error

EDIT_RECORD_FORMAT = "omrs-edit-record/1"
"""The format string every version 1 edit record line declares."""

EDIT_LOG_FILE = "edits.jsonl"
"""The edit log file name inside an experiment folder."""

_SHA256 = r"^[0-9a-f]{64}$"
# A plain file name: no path separator and no NUL. "." and ".." are refused below.
_PLAIN_NAME = r"^[^/\\\x00\r\n]+$"


class EditRecord(BaseModel):
    """One save of a file from the app."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["omrs-edit-record/1"]
    file: str = Field(pattern=_PLAIN_NAME)
    edited_at: datetime
    before_sha256: str = Field(pattern=_SHA256)
    after_sha256: str = Field(pattern=_SHA256)
    before_size: int = Field(ge=0)
    after_size: int = Field(ge=0)
    status: Status
    converted: bool
    tool: str = Field(min_length=1, pattern=ONE_LINE_PATTERN)

    @field_validator("file")
    @classmethod
    def _plain_name(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("file must be a plain file name")
        return value

    @field_validator("edited_at")
    @classmethod
    def _utc_only(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("edited_at must be in UTC")
        return value


def append_edit(folder: Path, record: EditRecord) -> None:
    """Append one edit record line to ``edits.jsonl`` in *folder*.

    Earlier lines are never changed. The file is created with mode 0644 when
    missing. A newline is written first when the file does not end with one.

    Args:
        folder: The experiment folder.
        record: The record to write.

    Raises:
        OSError: The log is a link or not a regular file, or the write failed.
    """
    line = (json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n").encode("utf-8")
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
    fd = os.open(folder / EDIT_LOG_FILE, flags, 0o644)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"{EDIT_LOG_FILE} is not a regular file")
        if info.st_size and os.pread(fd, 1, info.st_size - 1) != b"\n":
            line = b"\n" + line
        written = os.write(fd, line)
        if written != len(line):
            raise OSError(f"short write to {EDIT_LOG_FILE}")
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_text(folder: Path) -> str | None:
    """Return the log text, or None without a log. Refuse a link or a special file."""
    try:
        fd = os.open(folder / EDIT_LOG_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        if (folder / EDIT_LOG_FILE).is_symlink():
            raise RecordError(f"{EDIT_LOG_FILE} is a link, not a regular file") from None
        raise RecordError(f"{EDIT_LOG_FILE} cannot be read") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RecordError(f"{EDIT_LOG_FILE} is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read()
    finally:
        os.close(fd)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecordError(f"{EDIT_LOG_FILE} is not valid UTF-8: {exc.reason}") from None


def _parse_line(number: int, line: str) -> EditRecord:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RecordError(f"{EDIT_LOG_FILE} line {number} is not valid JSON: {exc}") from None
    check_format(data, EDIT_RECORD_FORMAT)
    try:
        return EditRecord.model_validate(data)
    except ValidationError as exc:
        message = describe_validation_error(exc)
        raise RecordError(f"{EDIT_LOG_FILE} line {number}: {message}") from None


def _lines(text: str) -> list[tuple[int, str]]:
    # Split on "\n" only: str.splitlines also splits on U+2028, U+2029 and
    # U+0085, which json.dumps(ensure_ascii=False) leaves raw inside a string.
    return [(n, line) for n, line in enumerate(text.split("\n"), start=1) if line.strip()]


def read_edits(folder: Path) -> tuple[EditRecord, ...]:
    """Read every edit record of an experiment folder, in file order.

    Args:
        folder: The experiment folder.

    Returns:
        The records. A missing file means no edits.

    Raises:
        UnsupportedFormatError: A line declares another format version.
        RecordError: The log is a link or not a regular file, or a line is
            not valid. The message names the line number.
    """
    text = _read_text(folder)
    if text is None:
        return ()
    return tuple(_parse_line(number, line) for number, line in _lines(text))


def edit_log_problems(folder: Path) -> list[str]:
    """Return one plain message for each problem in ``edits.jsonl``, or none.

    Unlike :func:`read_edits`, this reads past a bad line, so the checker can
    name every line that does not load.
    """
    try:
        text = _read_text(folder)
    except RecordError as exc:
        return [str(exc)]
    if text is None:
        return []
    problems = []
    for number, line in _lines(text):
        try:
            _parse_line(number, line)
        except RecordError as exc:
            message = str(exc)
            if not message.startswith(EDIT_LOG_FILE):
                message = f"{EDIT_LOG_FILE} line {number}: {message}"
            problems.append(message)
    return problems


def last_edit(folder: Path, name: str) -> EditRecord | None:
    """Return the newest edit record for the file *name*, or None.

    Lines that do not load are skipped, so a broken log never hides the file.
    The checker reports them.
    """
    try:
        text = _read_text(folder)
    except RecordError:
        return None
    if text is None:
        return None
    newest = None
    for number, line in _lines(text):
        try:
            record = _parse_line(number, line)
        except RecordError:
            continue
        if record.file == name:
            newest = record
    return newest
