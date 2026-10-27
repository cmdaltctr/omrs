"""Research experiment records, format ``omrs-experiment/1`` (design D1).

Pure core rules for the folders under ``experiments/``: the record model and
its generated JSON Schema, folder naming, detection, reserved numbers, run
records, the edit log, the checker, the generated index and the folder creator.

This package is not ``omrs.core.experiments``, which holds the approved
sandbox contexts for notebook runs. It reads and writes files only under the
directory a caller gives it. It starts no process and imports no web
framework or store; contract ``experiment-records-stay-pure`` enforces this.
Git facts for run records come from the caller.
"""

from __future__ import annotations

from .edit_log import (
    EDIT_LOG_FILE,
    EDIT_RECORD_FORMAT,
    EditRecord,
    append_edit,
    last_edit,
    read_edits,
)
from .record import (
    FORMAT,
    RECORD_FILE,
    Category,
    ExperimentRecord,
    MigrationNote,
    Purpose,
    RecordError,
    Refs,
    Size,
    Status,
    UnsupportedFormatError,
    dump_record,
    load_record,
    parse_record,
)

__all__ = [
    "EDIT_LOG_FILE",
    "EDIT_RECORD_FORMAT",
    "FORMAT",
    "RECORD_FILE",
    "Category",
    "EditRecord",
    "ExperimentRecord",
    "MigrationNote",
    "Purpose",
    "RecordError",
    "Refs",
    "Size",
    "Status",
    "UnsupportedFormatError",
    "append_edit",
    "dump_record",
    "last_edit",
    "load_record",
    "parse_record",
    "read_edits",
]
