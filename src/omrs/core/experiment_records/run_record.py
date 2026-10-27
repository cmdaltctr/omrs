"""Run records in ``output/run-records.jsonl`` (design D8).

Each run start appends one JSON line with the start time in UTC, the git
commit, whether the working tree had uncommitted changes, the SHA-256 of
``plan.json`` and the command. A run that checked a llama.cpp server also
stores an optional ``runtime`` key: the build and the ``{file, sha256}`` of
each model it found (reproducible-experiment-runtime, D5). JSON Lines is
append-only, so a resumed run never rewrites history. The checker compares
the recorded plan hash with the current ``plan.json`` to find a plan that
changed after a run.

This module never calls git. The caller passes the git facts
(``experiments/_lib/run_record.py`` reads them).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .record import RecordError, check_format, describe_validation_error
from .scan import OUTPUT_DIR

RUN_RECORD_FORMAT = "omrs-run-record/1"
"""The format string every version 1 run record line declares."""

RUN_RECORDS_FILE = "run-records.jsonl"
"""The run records file name inside ``output/``."""

PLAN_FILE = "plan.json"


_SHA256 = r"^[0-9a-f]{64}$"


class RunModel(BaseModel):
    """One model file a run found on the llama.cpp server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1)
    sha256: str = Field(pattern=_SHA256)


class RunUncheckedArm(BaseModel):
    """One arm of a runtime comparison that the llama.cpp check did not inspect.

    The values are the planned ones, so the run record still names the arm.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    version: str | None = None
    file: str = Field(min_length=1)
    sha256: str = Field(pattern=_SHA256)


class RunRuntime(BaseModel):
    """The llama.cpp build and model files a run found before it scored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    build: int = Field(ge=0, strict=True)
    models: tuple[RunModel, ...]
    unchecked: tuple[RunUncheckedArm, ...] = ()


class RunRecord(BaseModel):
    """One run start."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["omrs-run-record/1"]
    started_at: datetime
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    git_dirty: bool
    plan_sha256: str = Field(pattern=r"^(?:[0-9a-f]{64})?$")
    command: str = Field(min_length=1)
    runtime: RunRuntime | None = None

    @field_validator("started_at")
    @classmethod
    def _utc_only(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("started_at must be in UTC")
        return value


def plan_sha256(folder: Path) -> str:
    """Return the SHA-256 of ``plan.json`` in *folder*, or an empty string without one."""
    path = folder / PLAN_FILE
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_run_record(
    folder: Path,
    *,
    git_commit: str,
    git_dirty: bool,
    command: str,
    now: datetime | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> RunRecord:
    """Append one run record line to ``output/run-records.jsonl``.

    Earlier lines are never changed. ``output/`` is created when missing.

    Args:
        folder: The experiment folder.
        git_commit: The full commit hash the run starts from.
        git_dirty: True when the working tree had uncommitted changes.
        command: The command that started the run.
        now: The start time. It must carry a time zone. Defaults to the current time.
        runtime: The build and ``{file, sha256}`` list that the live-server
            check found. Left out of the line when None.

    Returns:
        The record that was written.

    Raises:
        ValueError: *now* has no time zone, or a field breaks a rule.
    """
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("the start time must carry a time zone")
    found = None
    if runtime is not None:
        try:
            found = RunRuntime.model_validate(runtime)
        except ValidationError as exc:
            raise ValueError(f"runtime: {describe_validation_error(exc)}") from None
    record = RunRecord(
        format=RUN_RECORD_FORMAT,
        started_at=now.astimezone(UTC),
        git_commit=git_commit,
        git_dirty=git_dirty,
        plan_sha256=plan_sha256(folder),
        command=command,
        runtime=found,
    )
    output = folder / OUTPUT_DIR
    output.mkdir(exist_ok=True)
    # Leave out empty optional keys, so a line keeps the shape older readers know.
    exclude: dict[str, Any] = {}
    if record.runtime is None:
        exclude["runtime"] = True
    elif not record.runtime.unchecked:
        exclude["runtime"] = {"unchecked"}
    line = json.dumps(record.model_dump(mode="json", exclude=exclude), ensure_ascii=False) + "\n"
    with (output / RUN_RECORDS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(line)
    return record


def read_run_records(folder: Path) -> tuple[RunRecord, ...]:
    """Read every run record of an experiment folder, in file order.

    Args:
        folder: The experiment folder.

    Returns:
        The records. A missing file means no runs.

    Raises:
        UnsupportedFormatError: A line declares another format version.
        RecordError: A line is not valid. The message names the line number.
    """
    path = folder / OUTPUT_DIR / RUN_RECORDS_FILE
    if not path.is_file():
        return ()
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecordError(f"{RUN_RECORDS_FILE} is not valid UTF-8: {exc.reason}") from None
    records = []
    # Split on "\n" only: str.splitlines also splits on U+2028, U+2029 and
    # U+0085, which json.dumps(ensure_ascii=False) leaves raw inside a string.
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RecordError(
                f"{RUN_RECORDS_FILE} line {number} is not valid JSON: {exc}"
            ) from None
        check_format(data, RUN_RECORD_FORMAT)
        try:
            records.append(RunRecord.model_validate(data))
        except ValidationError as exc:
            message = describe_validation_error(exc)
            raise RecordError(f"{RUN_RECORDS_FILE} line {number}: {message}") from None
    return tuple(records)
