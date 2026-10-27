"""Read and create experiments of one project for the web workspace (D4 to D7).

Every function takes the resolved ``experiments`` directory of a project and
scans it again, so the folders on disk stay the only record (design D4). The
returned dictionaries follow the response shapes of design D5.

File reading (design D6) serves only text files directly inside an experiment
folder. A name with a path separator, ``..``, a leading dot or a suffix outside
:data:`VIEWABLE_SUFFIXES` is refused before any file access. After links are
resolved, the file must still sit directly in its experiment folder, have no
leading dot and a served suffix. It is opened without following a link, and at
most :data:`MAX_FILE_BYTES` bytes are returned. An experiment folder or an
``output/`` folder that links to another place is not listed.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date as Date  # noqa: N812 - matches the record field name
from pathlib import Path
from typing import Any

from omrs.core.experiment_records.check import Finding, check_experiments
from omrs.core.experiment_records.index import (
    README_FILE,
    IndexFileError,
    IndexMarkerError,
    write_index,
)
from omrs.core.experiment_records.record import Category, Purpose, RecordError, Size
from omrs.core.experiment_records.reserved import load_reservations
from omrs.core.experiment_records.scaffold import ScaffoldError, create_experiment
from omrs.core.experiment_records.scan import (
    OUTPUT_DIR,
    ExperimentFolder,
    scan_experiments,
)

#: Suffixes whose text the workspace serves.
VIEWABLE_SUFFIXES = frozenset({".md", ".json", ".jsonl", ".txt", ".csv", ".yaml", ".yml", ".py"})
#: Most bytes of one file that the workspace returns (1 MiB).
MAX_FILE_BYTES = 1024 * 1024
#: The plain message when a new folder exists but the index was not updated.
INDEX_FAILED_MESSAGE = (
    f"The experiment folder was created, but the index in {README_FILE} was not updated. "
    "Run `omrs experiments index --write` to update it."
)
_MAX_NAME = 255


class ExperimentNotFoundError(KeyError):
    """The project has no experiment folder, or the folder no file, with this name."""


class ExperimentRefusedError(ValueError):
    """The request names something the workspace does not serve or cannot create.

    Nothing was read or written. The message holds no file system path.
    """


def check_name(name: str, what: str = "name") -> str:
    """Refuse a folder or file name before any file access.

    Raises:
        ExperimentRefusedError: The name is empty, too long, holds a path
            separator or ``..``, or starts with a dot.
    """
    if not name or len(name) > _MAX_NAME or "\x00" in name:
        raise ExperimentRefusedError(f"The {what} is empty, too long or not allowed.")
    if "/" in name or "\\" in name or ".." in name:
        raise ExperimentRefusedError(f"The {what} must not hold a path separator or '..'.")
    if name.startswith("."):
        raise ExperimentRefusedError(f"The {what} must not start with a dot.")
    return name


def finding_view(finding: Finding) -> dict[str, Any]:
    """Return one finding as ``{severity, code, folder, message}`` (top level: null folder)."""
    return {
        "severity": finding.severity,
        "code": finding.code,
        "folder": finding.folder or None,
        "message": finding.message,
    }


def experiment_view(folder: ExperimentFolder, findings: Iterable[Finding]) -> dict[str, Any]:
    """Map a loaded folder and its findings to the ``Experiment`` shape of design D5.

    Args:
        folder: A detected folder whose record loaded.
        findings: The checker findings of this folder.
    """
    record = folder.record
    assert record is not None  # noqa: S101 - callers pass loaded folders only
    refs = record.refs
    return {
        "folder": folder.name,
        "number": record.number,
        "title": record.title,
        "date": record.date.isoformat(),
        "category": record.category.value if record.category else None,
        "size": record.size.value if record.size else None,
        "purpose": record.effective_purpose.value,
        "status": record.status.value,
        "superseded_by": record.superseded_by,
        "finding": record.finding,
        "refs": None
        if refs is None
        else {"adrs": list(refs.adrs), "changes": list(refs.changes), "tasks": list(refs.tasks)},
        "migrated": record.migration is not None,
        "findings": [finding_view(item) for item in findings],
    }


def _by_folder(findings: Sequence[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.folder].append(finding)
    return grouped


def _inside(path: Path, parent: Path) -> bool:
    """Return True when *path* resolves to an entry directly inside *parent*."""
    return path.resolve().parent == parent


def _split(experiments: Path) -> tuple[list[ExperimentFolder], list[str]]:
    """Return the listed folders and the names of folders that link to another place.

    A listed folder has a valid record and resolves directly inside *experiments*.

    Raises:
        OSError: The directory or a folder in it cannot be read.
    """
    kept: list[ExperimentFolder] = []
    linked: list[str] = []
    for folder in scan_experiments(experiments):
        if not _inside(folder.path, experiments):
            linked.append(folder.name)
        elif folder.record is not None:
            kept.append(folder)
    return kept, linked


def _link_finding(name: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": "folder-link",
        "folder": None,
        "message": f"Folder {name} is a link to another place and is not listed.",
    }


def count_experiments(experiments: Path) -> int:
    """Return how many folders the library lists.

    Raises:
        OSError: The directory or a folder in it cannot be read.
    """
    return len(_split(experiments)[0])


def experiment_map(experiments: Path) -> dict[str, dict[str, Any]]:
    """Return every listed experiment by folder name, with its findings.

    Raises:
        OSError: The directory or a folder in it cannot be read.
    """
    kept, _ = _split(experiments)
    grouped = _by_folder(check_experiments(experiments))
    return {folder.name: experiment_view(folder, grouped.get(folder.name, ())) for folder in kept}


def library(experiments: Path) -> dict[str, Any]:
    """Return ``{experiments, reserved, findings}`` for one project.

    A folder without a valid record is not listed. Its findings join the
    project-level findings and keep the folder name, so the problem stays
    visible. A folder that links to another place is not listed either; one
    project-level finding names it and its own findings are left out.

    Raises:
        OSError: The directory or a folder in it cannot be read.
    """
    kept, linked = _split(experiments)
    findings = check_experiments(experiments)
    grouped = _by_folder(findings)
    hidden = {folder.name for folder in kept} | set(linked)
    try:
        reservations = load_reservations(experiments)
    except RecordError:
        reservations = ()  # the checker reports the broken file
    return {
        "experiments": [experiment_view(f, grouped.get(f.name, ())) for f in kept],
        "reserved": [entry.model_dump() for entry in reservations],
        "findings": [finding_view(item) for item in findings if item.folder not in hidden]
        + [_link_finding(name) for name in linked],
    }


def _folder(experiments: Path, name: str) -> tuple[ExperimentFolder, Path]:
    """Return a listed folder and its resolved path, directly inside *experiments*."""
    check_name(name, "folder name")
    kept, _ = _split(experiments)
    match = next((folder for folder in kept if folder.name == name), None)
    if match is None:
        raise ExperimentNotFoundError(name)
    return match, match.path.resolve(strict=True)


def experiment_folder(experiments: Path, name: str) -> Path:
    """Return the resolved path of a listed experiment folder, directly inside *experiments*.

    Raises:
        ExperimentRefusedError: The name is not a plain folder name.
        ExperimentNotFoundError: The project lists no experiment folder with this name.
    """
    path = _folder(experiments, name)[1]
    if path.parent != experiments.resolve():
        raise ExperimentNotFoundError(name)  # a link that leaves the experiments directory
    return path


def _served(target: Path, base: Path) -> bool:
    """Return True when a resolved *target* is a text file the workspace serves (D6).

    The target sits directly in *base*, its name has no leading dot and its
    suffix is in :data:`VIEWABLE_SUFFIXES`.
    """
    return (
        target.parent == base
        and not target.name.startswith(".")
        and target.suffix.lower() in VIEWABLE_SUFFIXES
    )


def _viewable(entry: Path, base: Path) -> bool:
    return entry.suffix.lower() in VIEWABLE_SUFFIXES and _served(entry.resolve(), base)


def experiment_detail(experiments: Path, name: str) -> dict[str, Any]:
    """Return ``{experiment, files, output}`` for one folder.

    ``files`` lists the top-level files without a leading dot, with their size
    and whether the workspace serves their text. ``output`` lists the names in
    ``output/``. It is None when the folder has no ``output/``, or when
    ``output/`` links to another place.

    Raises:
        ExperimentRefusedError: The name is not allowed.
        ExperimentNotFoundError: No listed experiment has this folder name.
    """
    folder, base = _folder(experiments, name)
    findings = [item for item in check_experiments(experiments) if item.folder == name]
    files = []
    for entry in sorted(base.iterdir(), key=lambda path: path.name):
        if entry.name.startswith(".") or not entry.is_file():
            continue
        viewable = _viewable(entry, base)
        # A link that is not served shows its own size, not the size of its target.
        size = entry.stat().st_size if viewable else entry.lstat().st_size
        files.append({"name": entry.name, "size": size, "viewable": viewable})
    output = base / OUTPUT_DIR
    has_output = output.is_dir() and _inside(output, base)
    return {
        "experiment": experiment_view(folder, findings),
        "files": files,
        "output": list(folder.output_names) if has_output else None,
    }


def read_regular_file(base: Path, name: str, limit: int = MAX_FILE_BYTES) -> tuple[bytes, int]:
    """Read at most ``limit + 1`` bytes of the regular file *name* directly in *base*.

    The file is opened relative to an open handle on *base* and without
    following a link, so a link swapped in after the earlier checks is refused.

    Returns:
        The bytes read and the full file size.

    Raises:
        ExperimentRefusedError: *name* is a link or not a regular file.
        ExperimentNotFoundError: The file does not exist.
    """
    directory = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            handle = os.open(name, flags, dir_fd=directory)
        except FileNotFoundError:
            raise ExperimentNotFoundError(name) from None
        except OSError:  # ELOOP: the name is a link
            raise ExperimentRefusedError("The workspace does not open this file.") from None
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode):
                raise ExperimentRefusedError("The workspace opens regular files only.")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining > 0:
                chunk = os.read(handle, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks), info.st_size
        finally:
            os.close(handle)
    finally:
        os.close(directory)


def read_file(experiments: Path, name: str, file_name: str) -> dict[str, Any]:
    """Return one top-level text file (design D6).

    The answer is ``{name, text, truncated, size, revision, editable,
    last_edited}``. ``revision`` is the SHA-256 of the file, or None when the
    text is cut. ``editable`` and ``last_edited`` come from
    :mod:`omrs.core.workspace.experiment_file_edits`.

    Raises:
        ExperimentRefusedError: The folder or file name is not allowed, the
            suffix is not served, or the file resolves to a file that is not
            served (outside the folder, in a subfolder, hidden or another kind).
        ExperimentNotFoundError: The folder or the file does not exist.
    """
    check_name(file_name, "file name")
    check_name(name, "folder name")
    if Path(file_name).suffix.lower() not in VIEWABLE_SUFFIXES:
        raise ExperimentRefusedError("The workspace does not open this kind of file.")
    _, base = _folder(experiments, name)
    try:
        target = (base / file_name).resolve(strict=True)
    except (OSError, RuntimeError):
        raise ExperimentNotFoundError(file_name) from None
    if not _served(target, base):
        raise ExperimentRefusedError("The file links to a file the workspace does not open.")
    data, size = read_regular_file(base, target.name)
    # Imported here: experiment_file_edits builds on this module.
    from .experiment_file_edits import is_editable, last_edited_view

    truncated = len(data) > MAX_FILE_BYTES
    return {
        "name": file_name,
        "text": data[:MAX_FILE_BYTES].decode("utf-8", errors="replace"),
        "truncated": truncated,
        "size": size,
        "revision": None if truncated else hashlib.sha256(data).hexdigest(),
        "editable": is_editable(base, file_name, data, size),
        "last_edited": last_edited_view(base, file_name),
    }


def new_experiment(
    experiments: Path,
    *,
    slug: str,
    title: str,
    category: Category,
    size: Size,
    day: Date,
    follow_up: str | None = None,
    purpose: Purpose = Purpose.OPTIMISATION,
) -> dict[str, Any]:
    """Create an experiment folder, then rewrite the index when it has markers (design D7).

    Returns:
        ``{folder, index}`` where ``index`` is ``written``, ``no-markers`` or
        ``no-readme``. When the index cannot be read or written, ``index`` is
        ``failed`` and ``message`` says how to fix it. The folder exists then.

    Raises:
        ExperimentRefusedError: The creator refused. Nothing was written.
    """
    try:
        folder = create_experiment(
            experiments,
            slug=slug,
            title=title,
            category=category,
            size=size,
            day=day,
            follow_up=follow_up,
            purpose=purpose,
        )
    except (ScaffoldError, RecordError) as exc:
        message = str(exc).replace(f" in {experiments}", "").replace(str(experiments), "folder")
        raise ExperimentRefusedError(message) from None
    readme = experiments / README_FILE
    if not readme.is_file():
        return {"folder": folder.name, "index": "no-readme"}
    try:
        write_index(readme, scan_experiments(experiments), load_reservations(experiments))
    except IndexMarkerError:
        return {"folder": folder.name, "index": "no-markers"}
    except (IndexFileError, OSError):
        # IndexFileError here means the file is not valid UTF-8.
        return {"folder": folder.name, "index": "failed", "message": INDEX_FAILED_MESSAGE}
    return {"folder": folder.name, "index": "written"}
