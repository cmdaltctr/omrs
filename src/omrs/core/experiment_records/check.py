"""The experiments checker (spec "The checker reports problems").

The checker reads the experiments directory and returns findings. It writes
no file. Each finding has a severity (``error``, ``warning`` or ``info``), a
stable code, the experiment folder (empty for directory-level findings) and
a plain message.

Codes:

- ``record-missing``, ``record-invalid`` (error): no valid ``experiment.json``.
- ``folder-name`` (warning): a folder with a record follows no name pattern.
- ``number-mismatch``, ``date-mismatch`` (error): the record differs from the folder name.
- ``superseded-target-missing`` (error): ``superseded_by`` names no other detected
  experiment folder (a missing folder, a shared folder such as ``_lib/``, or itself).
- ``number-shared`` (error on a record without a migration note, else warning).
- ``report-status`` (warning, info on converted records): the ``report.md``
  header names another status.
- ``plan-changed`` (warning): ``plan.json`` changed after a recorded run.
- ``run-records-invalid`` (warning): ``output/run-records.jsonl`` cannot be read.
- ``edit-log-invalid`` (warning): a line of ``edits.jsonl`` does not load, or the
  file is a link or not a regular file.
- ``files-missing`` (warning, info on converted records): a file the size needs is missing.
- ``size-missing``, ``category-missing`` (info): a converted record leaves the field empty.
- ``index-stale``, ``index-markers`` (error), ``index-missing`` (warning): ``EXP_README.md``.
- ``reserved-invalid`` (error), ``reserved-has-folder`` (info): ``reserved.json``.
- ``publication-not-confirmatory`` (error): a ``publication`` experiment is not Confirmatory.
- ``publication-plan-unreadable`` (error): a ``publication`` experiment has no readable
  ``plan.json`` object.
- ``publication-runtime-missing`` (error): the ``plan.json`` of a ``publication``
  experiment has no ``runtime`` block.
- ``publication-runtime-invalid`` (error): that ``runtime`` block breaks a rule of
  ``runtime_block.py``, for example a local model that does not run through llama.cpp.

The ``publication-*`` rules skip ``optimisation`` records and records without
a purpose (reproducible-experiment-runtime, design D3).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .edit_log import edit_log_problems
from .index import README_FILE, IndexMarkerError, index_is_current
from .record import Purpose, RecordError, Size, read_json
from .reserved import RESERVED_FILE, Reservation, load_reservations
from .run_record import PLAN_FILE, RUN_RECORDS_FILE, plan_sha256, read_run_records
from .runtime_block import RUNTIME_KEY, load_runtime_block
from .scan import ExperimentFolder, scan_experiments

Severity = Literal["error", "warning", "info"]

REQUIRED_FILES: dict[Size, tuple[str, ...]] = {
    Size.QUICK: ("report.md",),
    Size.STANDARD: ("protocol.md", "plan.json", "report.md"),
    Size.CONFIRMATORY: ("protocol.md", "plan.json", "report.md"),
}

_STATUS_LINE = re.compile(r"^\s*(?:[-*]\s+)?\*\*Status(?::\*\*|\*\*:)\s*(?P<value>.*)$")
_FIRST_WORD = re.compile(r"[A-Za-z]+")


class Finding(BaseModel):
    """One problem the checker found."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Severity
    code: str
    folder: str
    message: str


def has_failures(findings: Sequence[Finding], *, strict: bool) -> bool:
    """Return True when a finding is an error, or a warning in strict mode."""
    failing = {"error", "warning"} if strict else {"error"}
    return any(finding.severity in failing for finding in findings)


def report_status(report: Path) -> str | None:
    """Return the first word of the ``Status`` line in the header block of *report*.

    The header block is every line before the first ``## `` heading. Returns
    None when the file or the line is absent.
    """
    if not report.is_file():
        return None
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            return None
        match = _STATUS_LINE.match(line)
        if match:
            word = _FIRST_WORD.match(match.group("value").strip())
            return word.group(0) if word else match.group("value").strip()
    return None


def _soft(folder: ExperimentFolder) -> Severity:
    """Warning on a new record, information on a converted one."""
    return "info" if folder.is_converted else "warning"


def _name_rules(folder: ExperimentFolder) -> Iterator[Finding]:
    record = folder.record
    assert record is not None  # noqa: S101 - callers pass loaded folders only
    if folder.parsed is None:
        yield Finding(
            severity="warning",
            code="folder-name",
            folder=folder.name,
            message="the folder name does not follow <number>-<slug>-<YYYY-MM-DD>",
        )
        return
    if record.number != folder.parsed.number:
        yield Finding(
            severity="error",
            code="number-mismatch",
            folder=folder.name,
            message=f"the record number {record.number!r} differs from the folder name "
            f"number {folder.parsed.number!r}",
        )
    if record.date != folder.parsed.date:
        yield Finding(
            severity="error",
            code="date-mismatch",
            folder=folder.name,
            message=f"the record date {record.date} differs from the folder name "
            f"date {folder.parsed.date}",
        )


def _superseded_problem(target: str, folder: str, experiments: set[str]) -> str | None:
    if target == folder:
        return "superseded_by names its own folder; name the experiment that replaces it"
    if target not in experiments:
        return f"the superseding folder {target} is not an experiment folder in this directory"
    return None


def _content_rules(folder: ExperimentFolder, experiments: set[str]) -> Iterator[Finding]:
    record = folder.record
    assert record is not None  # noqa: S101 - callers pass loaded folders only
    problem = (
        _superseded_problem(record.superseded_by, folder.name, experiments)
        if record.superseded_by
        else None
    )
    if problem is not None:
        yield Finding(
            severity="error",
            code="superseded-target-missing",
            folder=folder.name,
            message=problem,
        )
    status = report_status(folder.path / "report.md")
    if status is not None and status != record.status.value:
        yield Finding(
            severity=_soft(folder),
            code="report-status",
            folder=folder.name,
            message=f"report.md says {status}, but experiment.json says {record.status.value}",
        )
    for field in ("size", "category"):
        if getattr(record, field) is None:
            yield Finding(
                severity="info",
                code=f"{field}-missing",
                folder=folder.name,
                message=f"the converted record has no {field}",
            )
    if record.size is not None:
        missing = [f for f in REQUIRED_FILES[record.size] if not (folder.path / f).is_file()]
        if missing:
            yield Finding(
                severity=_soft(folder),
                code="files-missing",
                folder=folder.name,
                message=f"a {record.size.value} experiment needs {', '.join(missing)}",
            )


def _run_rules(folder: ExperimentFolder) -> Iterator[Finding]:
    if RUN_RECORDS_FILE not in folder.output_names:
        return
    try:
        runs = read_run_records(folder.path)
    except RecordError as exc:
        yield Finding(
            severity="warning", code="run-records-invalid", folder=folder.name, message=str(exc)
        )
        return
    current = plan_sha256(folder.path)
    changed = sum(1 for run in runs if run.plan_sha256 != current)
    if changed:
        yield Finding(
            severity="warning",
            code="plan-changed",
            folder=folder.name,
            message=f"plan.json differs from the plan of {changed} of {len(runs)} recorded runs",
        )


def _publication_rules(folder: ExperimentFolder) -> Iterator[Finding]:
    record = folder.record
    assert record is not None  # noqa: S101 - callers pass loaded folders only
    if record.effective_purpose is not Purpose.PUBLICATION:
        return
    name = folder.name
    if record.size is not Size.CONFIRMATORY:
        size = record.size.value if record.size is not None else "not set"
        yield Finding(
            severity="error",
            code="publication-not-confirmatory",
            folder=name,
            message=f"{name}: a publication experiment must be Confirmatory, "
            f"so its protocol and plan are committed before the first run; its size is {size}",
        )
    try:
        plan = read_json(folder.path / PLAN_FILE)
    except RecordError as exc:
        plan, problem = None, str(exc)
    else:
        problem = f"{PLAN_FILE} does not hold a JSON object"
    if not isinstance(plan, dict):
        yield Finding(
            severity="error",
            code="publication-plan-unreadable",
            folder=name,
            message=f"{name}: a publication experiment needs a readable {PLAN_FILE} with a "
            f"{RUNTIME_KEY} block that pins its local models; {problem}",
        )
        return
    if RUNTIME_KEY not in plan:
        yield Finding(
            severity="error",
            code="publication-runtime-missing",
            folder=name,
            message=f"{name}: a publication experiment needs a {RUNTIME_KEY} block in "
            f"{PLAN_FILE} that pins each local model to a llama.cpp GGUF file and build",
        )
        return
    try:
        load_runtime_block(plan)
    except RecordError as exc:
        yield Finding(
            severity="error",
            code="publication-runtime-invalid",
            folder=name,
            message=f"{name}: the {RUNTIME_KEY} block in {PLAN_FILE} breaks the local-runtime "
            f"rule of a publication experiment: {exc}",
        )


def _edit_log_rules(folder: ExperimentFolder) -> Iterator[Finding]:
    for message in edit_log_problems(folder.path):
        yield Finding(
            severity="warning", code="edit-log-invalid", folder=folder.name, message=message
        )


def _shared_numbers(folders: Sequence[ExperimentFolder]) -> dict[str, list[Finding]]:
    groups: dict[str, list[ExperimentFolder]] = defaultdict(list)
    for folder in folders:
        if folder.record is not None and folder.record.number:
            groups[folder.record.number].append(folder)
    found: dict[str, list[Finding]] = defaultdict(list)
    for number, members in groups.items():
        if len(members) < 2:
            continue
        for folder in members:
            others = ", ".join(other.name for other in members if other is not folder)
            found[folder.name].append(
                Finding(
                    severity="warning" if folder.is_converted else "error",
                    code="number-shared",
                    folder=folder.name,
                    message=f"number {number} is also used by {others}",
                )
            )
    return found


def _reserved_rules(
    folders: Sequence[ExperimentFolder], reservations: Sequence[Reservation]
) -> dict[str, list[Finding]]:
    reserved = {entry.number: entry for entry in reservations}
    found: dict[str, list[Finding]] = defaultdict(list)
    for folder in folders:
        entry = reserved.get(folder.number)
        if folder.number and entry is not None:
            found[folder.name].append(
                Finding(
                    severity="info",
                    code="reserved-has-folder",
                    folder=folder.name,
                    message=f"number {entry.number} is still listed in {RESERVED_FILE} "
                    f"({entry.reason}); remove the reservation",
                )
            )
    return found


def _index_rules(
    root: Path, folders: Sequence[ExperimentFolder], reservations: Sequence[Reservation]
) -> Iterator[Finding]:
    readme = root / README_FILE
    if not readme.is_file():
        yield Finding(
            severity="warning",
            code="index-missing",
            folder="",
            message=f"{README_FILE} is missing, so there is no index to check",
        )
        return
    text = readme.read_bytes().decode("utf-8", errors="replace")
    try:
        current = index_is_current(text, folders, reservations)
    except IndexMarkerError as exc:
        yield Finding(severity="error", code="index-markers", folder="", message=str(exc))
        return
    if not current:
        yield Finding(
            severity="error",
            code="index-stale",
            folder="",
            message=f"the index in {README_FILE} differs from the records; "
            "run `omrs experiments index --write`",
        )


def check_experiments(root: Path) -> tuple[Finding, ...]:
    """Check every experiment folder under *root*. Write nothing.

    Args:
        root: The experiments directory.

    Returns:
        Directory-level findings first, then each folder's findings in
        natural folder order.

    Raises:
        NotADirectoryError: *root* is not a directory.
    """
    folders = scan_experiments(root)
    findings: list[Finding] = []
    try:
        reservations = load_reservations(root)
    except RecordError as exc:
        reservations = ()
        findings.append(
            Finding(severity="error", code="reserved-invalid", folder="", message=str(exc))
        )
    findings.extend(_index_rules(root, folders, reservations))
    shared = _shared_numbers(folders)
    experiments = {folder.name for folder in folders}
    reserved = _reserved_rules(folders, reservations)
    for folder in folders:
        if folder.record is None:
            code = "record-invalid" if folder.has_record_file else "record-missing"
            message = folder.record_error or "experiment.json is missing"
            findings.append(
                Finding(severity="error", code=code, folder=folder.name, message=message)
            )
            continue
        findings.extend(_name_rules(folder))
        findings.extend(_content_rules(folder, experiments))
        findings.extend(_run_rules(folder))
        findings.extend(_publication_rules(folder))
        findings.extend(_edit_log_rules(folder))
        findings.extend(shared.get(folder.name, ()))
        findings.extend(reserved.get(folder.name, ()))
    return tuple(findings)
