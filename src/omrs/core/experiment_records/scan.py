"""Detect experiment folders and load their records (spec "Experiment folders").

A direct subfolder of the experiments directory is an experiment when it
holds ``experiment.json``, or when its name follows
``<number>-<slug>-<YYYY-MM-DD>``. Every other subfolder (``_lib/``,
``ARCHIVED/``, ``example/``) is ignored. Detection lists only the top level
of an experiment's ``output/`` folder and opens nothing inside it, because
``output/`` can hold many gigabytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .naming import FolderName, folder_sort_key, parse_folder_name
from .record import RECORD_FILE, ExperimentRecord, RecordError, load_record

OUTPUT_DIR = "output"


@dataclass(frozen=True)
class ExperimentFolder:
    """One detected experiment folder.

    Attributes:
        name: The folder name, which is the experiment's identity.
        path: The folder path.
        parsed: The parts of the folder name, or None when it follows no pattern.
        record: The loaded record, or None when it is missing or invalid.
        record_error: Why the record did not load, or None when it loaded.
        has_record_file: True when ``experiment.json`` exists.
        output_names: The names directly inside ``output/``, sorted.
    """

    name: str
    path: Path
    parsed: FolderName | None
    record: ExperimentRecord | None
    record_error: str | None
    has_record_file: bool
    output_names: tuple[str, ...]

    @property
    def number(self) -> str:
        """The record number, else the number in the folder name, else empty."""
        if self.record is not None:
            return self.record.number
        return self.parsed.number if self.parsed is not None else ""

    @property
    def is_converted(self) -> bool:
        """True when the record carries a migration note."""
        return self.record is not None and self.record.migration is not None


def _output_names(folder: Path) -> tuple[str, ...]:
    output = folder / OUTPUT_DIR
    if not output.is_dir():
        return ()
    return tuple(sorted(entry.name for entry in output.iterdir()))


def _load(folder: Path) -> tuple[ExperimentRecord | None, str | None]:
    path = folder / RECORD_FILE
    if not path.is_file():
        return None, f"{RECORD_FILE} is missing"
    try:
        return load_record(path), None
    except RecordError as exc:
        return None, f"{RECORD_FILE} is not valid: {exc}"


def read_folder(path: Path) -> ExperimentFolder:
    """Load one folder's record and output names, without judging the folder.

    Args:
        path: The experiment folder.

    Returns:
        The folder facts. A missing or invalid record is described in
        ``record_error``; it is never raised.
    """
    record, error = _load(path)
    return ExperimentFolder(
        name=path.name,
        path=path,
        parsed=parse_folder_name(path.name),
        record=record,
        record_error=error,
        has_record_file=(path / RECORD_FILE).is_file(),
        output_names=_output_names(path),
    )


def is_experiment_folder(path: Path) -> bool:
    """Return True when *path* is a folder with a record or a numbered folder name."""
    if not path.is_dir():
        return False
    if (path / RECORD_FILE).is_file():
        return True
    parsed = parse_folder_name(path.name)
    return parsed is not None and parsed.number != ""


def scan_experiments(root: Path) -> tuple[ExperimentFolder, ...]:
    """Detect and load every experiment folder directly under *root*.

    Args:
        root: The experiments directory.

    Returns:
        The folders in natural number order, then folder name. Unnumbered
        folders come last.

    Raises:
        NotADirectoryError: *root* is not a directory.
    """
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")
    folders = [read_folder(path) for path in root.iterdir() if is_experiment_folder(path)]
    return tuple(sorted(folders, key=lambda folder: folder_sort_key(folder.number, folder.name)))
