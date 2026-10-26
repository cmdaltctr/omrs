"""Save ``protocol.md`` and the report of an experiment (edit-experiment-files-in-library).

The web workspace edits three fixed names only: ``protocol.md``, ``report.md``,
and ``results.md`` when the folder has no ``report.md`` (design D1). A file is
editable when it exists as a regular file directly in a listed experiment
folder, is at most :data:`MAX_FILE_BYTES` and decodes as strict UTF-8.

A save carries the SHA-256 revision that the editor loaded (design D4). The
new bytes go to a temporary file in the same folder, which then replaces the
file in one rename. One line is then appended to ``edits.jsonl``. When the
append fails, the old bytes are put back. ``experiment.json`` never changes.

This module never runs git. The caller passes the tool string, because
``core/`` does not import the package version, and holds one lock per
experiment folder so that two saves do not interleave.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from omrs.core.experiment_records.edit_log import (
    EDIT_LOG_FILE,
    EDIT_RECORD_FORMAT,
    EditRecord,
    append_edit,
    last_edit,
)
from omrs.core.experiment_records.record import ExperimentRecord

from .experiment_pages import (
    MAX_FILE_BYTES,
    ExperimentNotFoundError,
    ExperimentRefusedError,
    _folder,
    check_name,
    read_regular_file,
)

#: Every name the workspace may save. ``results.md`` only without ``report.md``.
EDITABLE_NAMES = frozenset({"protocol.md", "report.md", "results.md"})
#: The 500 message when the new file could not be written. The old text stays.
WRITE_FAILED = "The file was not saved."
#: The 500 message when the edit could not be recorded and the old text is back.
NOT_SAVED = "The file was not saved, because the app could not record the edit in edits.jsonl."
#: The 500 message when the edit could not be recorded and the old text could not be put back.
SAVED_NOT_RECORDED = (
    "The file was saved, but the edit was not recorded in edits.jsonl. "
    "Run git diff on the file to see the change."
)
_NOT_EDITABLE = (
    "The workspace edits only an existing protocol.md or report file of up to 1 MiB in UTF-8."
)
_BOM = b"\xef\xbb\xbf"

EditConflict = Literal["changed_on_disk", "edit_log_unusable"]


class ExperimentEditConflictError(Exception):
    """The save was refused because of the state on disk. Nothing was written."""

    def __init__(self, reason: EditConflict) -> None:
        super().__init__(reason)
        self.reason: EditConflict = reason


class ExperimentEditFailedError(Exception):
    """The save failed part way. The message says whether the file changed."""


def editable_names(base: Path) -> frozenset[str]:
    """Return the names the workspace may save in the experiment folder *base*."""
    report = os.path.lexists(base / "report.md")
    return frozenset({"protocol.md", "report.md"} if report else {"protocol.md", "results.md"})


def is_editable(base: Path, name: str, data: bytes, size: int) -> bool:
    """Return True when the file *name* with the read *data* and full *size* is editable."""
    if name not in editable_names(base) or (base / name).is_symlink():
        return False
    if size > MAX_FILE_BYTES or len(data) > MAX_FILE_BYTES:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _edit_view(record: EditRecord) -> dict[str, Any]:
    return {
        "edited_at": record.edited_at.isoformat().replace("+00:00", "Z"),
        "status": record.status.value,
        "converted": record.converted,
    }


def last_edited_view(base: Path, name: str) -> dict[str, Any] | None:
    """Return ``{edited_at, status, converted}`` of the newest logged save of *name*, or None."""
    record = last_edit(base, name)
    return None if record is None else _edit_view(record)


def _check_text(text: str) -> None:
    if "\x00" in text:
        raise ExperimentRefusedError("The text must not hold a NUL character.")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ExperimentRefusedError("The text is larger than 1 MiB.")


def _new_bytes(text: str, old: bytes) -> bytes:
    """Build the bytes to save: keep the old CRLF line endings and byte order mark (D5)."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    body = old.removeprefix(_BOM)
    if body.count(b"\n") and body.count(b"\n") == body.count(b"\r\n"):
        text = text.replace("\n", "\r\n")
    data = (_BOM if old.startswith(_BOM) else b"") + text.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ExperimentRefusedError("The text is larger than 1 MiB.")
    return data


def _check_log(base: Path) -> None:
    path = base / EDIT_LOG_FILE
    if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
        raise ExperimentEditConflictError("edit_log_unusable")


def _read_current(base: Path, name: str) -> bytes:
    try:
        data, size = read_regular_file(base, name)
    except ExperimentNotFoundError:
        raise ExperimentRefusedError(_NOT_EDITABLE) from None
    if not is_editable(base, name, data, size):
        raise ExperimentRefusedError(_NOT_EDITABLE)
    return data


def _replace(base: Path, name: str, data: bytes, expected: str) -> None:
    """Write *data* to a temporary file, then rename it over *name* if *name* is unchanged.

    Raises:
        ExperimentEditConflictError: *name* no longer has the SHA-256 *expected*.
        OSError: A write or the rename failed. No temporary file is left.
    """
    directory = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    temporary = f".{name}.omrs-edit-{secrets.token_hex(8)}.tmp"
    try:
        mode = stat.S_IMODE(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        handle = os.open(temporary, flags, 0o600, dir_fd=directory)
        try:
            os.fchmod(handle, mode)
            view = memoryview(data)
            while view:
                view = view[os.write(handle, view) :]
            os.fsync(handle)
        finally:
            os.close(handle)
        if hashlib.sha256(read_regular_file(base, name)[0]).hexdigest() != expected:
            raise ExperimentEditConflictError("changed_on_disk")
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(directory)


def _log_or_restore(base: Path, name: str, old: bytes, entry: EditRecord) -> None:
    try:
        append_edit(base, entry)
        return
    except OSError:
        pass
    try:
        _replace(base, name, old, entry.after_sha256)
    except (OSError, ExperimentEditConflictError, ExperimentRefusedError):
        raise ExperimentEditFailedError(SAVED_NOT_RECORDED) from None
    raise ExperimentEditFailedError(NOT_SAVED)


def save_file(
    experiments: Path,
    folder: str,
    name: str,
    text: str,
    base_revision: str,
    tool: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save *text* as the file *name* of one experiment folder (design D4).

    Args:
        experiments: The resolved experiments directory of an added project.
        folder: The experiment folder name.
        name: ``protocol.md``, ``report.md`` or ``results.md``.
        text: The new text, as the editor sends it.
        base_revision: The SHA-256 of the file when the editor loaded it.
        tool: One line that names the saving tool, for the edit log.
        now: The save time. Defaults to the current time.

    Returns:
        ``{name, revision, size, changed, last_edited}``.

    Raises:
        ExperimentRefusedError: The name, the file or the text is not allowed.
            Nothing was read or written.
        ExperimentNotFoundError: The project lists no experiment folder *folder*.
        ExperimentEditConflictError: The file changed on disk, or the edit log
            is a link or not a regular file. Nothing was written.
        ExperimentEditFailedError: The edit could not be recorded.
    """
    check_name(name, "file name")
    if name not in EDITABLE_NAMES:
        raise ExperimentRefusedError(_NOT_EDITABLE)
    _check_text(text)
    match, base = _folder(experiments, folder)
    if base.parent != experiments.resolve():
        raise ExperimentNotFoundError(folder)
    if name not in editable_names(base):
        raise ExperimentRefusedError(_NOT_EDITABLE)
    _check_log(base)
    old = _read_current(base, name)
    old_revision = hashlib.sha256(old).hexdigest()
    if old_revision != base_revision:
        raise ExperimentEditConflictError("changed_on_disk")
    new = _new_bytes(text, old)
    if new == old:
        return {
            "name": name,
            "revision": old_revision,
            "size": len(old),
            "changed": False,
            "last_edited": last_edited_view(base, name),
        }
    try:
        _replace(base, name, new, old_revision)
    except OSError:
        raise ExperimentEditFailedError(WRITE_FAILED) from None
    entry = _entry(match.record, name, old, new, tool, now)
    _log_or_restore(base, name, old, entry)
    return {
        "name": name,
        "revision": entry.after_sha256,
        "size": len(new),
        "changed": True,
        "last_edited": _edit_view(entry),
    }


def _entry(
    record: ExperimentRecord | None,
    name: str,
    old: bytes,
    new: bytes,
    tool: str,
    now: datetime | None,
) -> EditRecord:
    assert record is not None  # noqa: S101 - listed folders have a loaded record
    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    return EditRecord(
        format=EDIT_RECORD_FORMAT,
        file=name,
        edited_at=moment,
        before_sha256=hashlib.sha256(old).hexdigest(),
        after_sha256=hashlib.sha256(new).hexdigest(),
        before_size=len(old),
        after_size=len(new),
        status=record.status,
        converted=record.migration is not None,
        tool=tool,
    )
