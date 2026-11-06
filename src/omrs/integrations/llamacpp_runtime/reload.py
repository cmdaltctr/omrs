"""The reload rule: rewrite only changed sections, then ask the router to reload (design D7).

A preset change of one entry (file, projector or preset values) rewrites only
that entry's section of ``models.ini`` and calls ``GET /models?reload=1``.
b11941 unloads only the changed model; the next request loads the new preset
(spike 1.2). A change of a model another process uses fails for that model
only (``version-busy``). Router arguments never change here: they are in the
router digest, so a change there is a new router version and restarts it.

Every function here runs under the router's ``start.lock``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from . import process, readiness
from .locks import LockFile
from .model_locks import ModelHolds
from .preset_writer import (
    read_preset,
    replace_section,
    section_digest,
    split_sections,
    write_preset,
)
from .state import ServerRecord, read_server_record, write_server_record


def running_record(folder: Path) -> ServerRecord | None:
    """Return the record of a router that runs and is ours, else ``None``."""
    record = read_server_record(folder)
    if record is None or record.state != "running" or not process.owns(record.pid, record.binary):
        return None
    return record


def sections_in_use(folder: Path, wanted: Mapping[str, str], holds: ModelHolds) -> dict[str, str]:
    """Return the ``models.ini`` sections a start must keep: ``{model: section}``.

    A start writes the whole file. After a crash, other processes still hold
    models with the sections in force. A section that differs from *wanted*
    (``""`` or absent means this process lists no section) stays when another
    process uses its model, as in :func:`apply_sections`. A section no other
    process uses is free, and this process's hold on it is kept.
    """
    kept: dict[str, str] = {}
    for model, section in split_sections(read_preset(folder)).items():
        if wanted.get(model, "") == section:
            continue
        was_held = holds.held(model)
        probe = holds.take_exclusive(model)
        if probe is None:
            kept[model] = section
        elif was_held and wanted.get(model):
            holds.keep(model, probe)
        else:
            probe.close()
    return kept


def apply_sections(
    folder: Path, wanted: Mapping[str, str], holds: ModelHolds, busy: Mapping[str, int]
) -> dict[str, str]:
    """Bring the running router's sections to *wanted*, one model at a time.

    Args:
        folder: The router folder.
        wanted: ``{model: section text}``; ``""`` means the section must go.
        holds: This process's model holds.
        busy: ``{model: requests in flight in this process}``; a model with
            requests in flight is not changed under them.

    Returns:
        ``{model: outcome}`` with ``unchanged``, ``reloaded``, ``added``,
        ``removed`` or ``version-busy``, for each model in *wanted*.
    """
    record = running_record(folder)
    text = read_preset(folder)
    have = split_sections(text)
    result: dict[str, str] = {}
    probes: dict[str, tuple[LockFile, bool]] = {}
    for model, section in wanted.items():
        current = have.get(model, "")
        if section == current:
            result[model] = "unchanged"
            continue
        was_held = holds.held(model)
        probe = None if busy.get(model, 0) > 0 else holds.take_exclusive(model)
        if probe is None:
            result[model] = "version-busy"
            continue
        probes[model] = (probe, was_held)
        text = replace_section(text, model, section or None)
        result[model] = "removed" if not section else ("added" if not current else "reloaded")
    try:
        if probes:
            write_preset(folder, text)
            if record is not None:
                readiness.reload_presets(f"http://127.0.0.1:{record.port}")
                record.models = {n: section_digest(s) for n, s in split_sections(text).items()}
                write_server_record(folder, record)
    finally:
        for model, (probe, was_held) in probes.items():
            if was_held and wanted.get(model):
                holds.keep(model, probe)
            else:
                probe.close()
    return result
