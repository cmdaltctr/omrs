"""The ``models.ini`` writer of the router (design D4, D5; task 3.3).

One section per usable list entry, named by its ``model``::

    [Qwen/Qwen3-4B-GGUF:Q8_0]
    model = /m/Qwen3-4B-Q8_0.gguf
    ctx-size = 32768
    parallel = 2

``model`` and ``mmproj`` come first, then the allow-listed preset keys in the
fixed order of :data:`omrs.config.llamacpp_preset.PRESET_KEYS` (the single
source of keys, types and ranges). Booleans are written exactly ``true`` or
``false``, never as a negated key. No ``[*]`` section is written.

An entry with no file is left out as ``not-downloaded``. An entry that fails a
check is left out with a fixed reason (``model-invalid``, ``preset-invalid``,
``file-changed``); the other entries still serve. The file is written to a
temporary file and renamed.

Entries are plain data with the fields of ``config.llamacpp_models``'s
``LlamaCppModelEntry`` (``model``, ``file``, ``projector``, ``sha256``,
``projector_sha256``, ``preset``). Compose has already checked them; the
writer checks again because a file can change after a save.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from omrs.config.llamacpp_preset import PRESET_KEYS, preset_problems

from .hashes import HashCache
from .model_reasons import model_reason_text
from .router_spec import PRESET_FILE

#: The note of an entry that runs without a recorded SHA-256.
NOT_CHECKED_NOTE = "File not checked"

EntryState = Literal["listed", "not-downloaded", "failed"]

#: Characters that would end an INI value or start a comment or section.
_INI_BREAK = re.compile(r"[\r\n\x00;#\[\]]")


class EntryLike(Protocol):
    """The fields the writer reads from one list entry."""

    model: str
    file: str | None
    projector: str | None
    sha256: str | None
    projector_sha256: str | None
    preset: Mapping[str, Any]


@dataclass(frozen=True)
class EntryOutcome:
    """What the writer did with one entry.

    Attributes:
        model: The entry's model name.
        state: ``listed`` (a section was written), ``not-downloaded`` or ``failed``.
        reason: The fixed reason of a failed entry, else ``None``.
        reason_text: The plain-English line of *reason*, else ``""``.
        note: ``"File not checked"`` for an entry with no recorded SHA-256.
        section: The section text, ``""`` when left out.
        one_slot: Whether the entry sets ``parallel = 1`` (its requests serialise).
    """

    model: str
    state: EntryState
    reason: str | None = None
    reason_text: str = ""
    note: str | None = None
    section: str = ""
    one_slot: bool = False

    @property
    def digest(self) -> str | None:
        """The model digest: SHA-256 of the section text (design D8)."""
        return section_digest(self.section) if self.section else None


@dataclass(frozen=True)
class PresetPlan:
    """The outcome of every entry, in list order."""

    outcomes: tuple[EntryOutcome, ...]

    @property
    def text(self) -> str:
        """The ``models.ini`` text: the written sections, one blank line apart."""
        return join_sections(o.section for o in self.outcomes if o.section)

    @property
    def digests(self) -> dict[str, str]:
        """``{model: digest}`` of the written sections."""
        return {o.model: o.digest for o in self.outcomes if o.digest is not None}

    def outcome(self, model: str) -> EntryOutcome | None:
        """Return the outcome of *model*, or ``None`` when it is not listed."""
        return next((o for o in self.outcomes if o.model == model), None)


def section_digest(section: str) -> str:
    """Return the SHA-256 of one section's text."""
    return hashlib.sha256(section.encode("utf-8")).hexdigest()


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def format_section(entry: EntryLike) -> str:
    """Return the section text of *entry*, with no disk check.

    Raises:
        ValueError: A preset key is outside the allow-list or a value breaks
            its rule, or the name or a path would break the INI line.
    """
    preset = dict(entry.preset or {})
    problems = preset_problems(preset)
    if problems:
        raise ValueError(f"the preset breaks the allow-list: {problems[0].rule}")
    lines = [f"[{entry.model}]", f"model = {entry.file}"]
    if entry.projector:
        lines.append(f"mmproj = {entry.projector}")
    lines += [f"{name} = {_value(preset[name])}" for name in PRESET_KEYS if name in preset]
    for text in (entry.model, entry.file or "", entry.projector or ""):
        if _INI_BREAK.search(text) or text != text.strip():
            raise ValueError(
                "the model name or a path holds a character the preset file cannot hold"
            )
    return "\n".join(lines) + "\n"


def _path_problem(path: str, *, projector: bool) -> str | None:
    """Return the file name when *path* breaks the file rule now, else ``None``."""
    name = os.path.basename(path)
    if (
        not os.path.isabs(path)
        or not name.lower().endswith(".gguf")
        or (not projector and "mmproj" in name.lower())
        or _INI_BREAK.search(path)
        or path != path.strip()
        or not os.path.isfile(path)
        or not os.access(path, os.R_OK)
    ):
        return name or path
    return None


def _failed(entry: EntryLike, reason: str, detail: str = "") -> EntryOutcome:
    return EntryOutcome(entry.model, "failed", reason, model_reason_text(reason, detail))


def _check_hashes(entry: EntryLike, decision: bool, hashes: HashCache) -> EntryOutcome | None:
    """Return a failed outcome when a recorded SHA-256 differs or a decision hash is missing."""
    pairs = [(entry.file or "", entry.sha256)]
    if entry.projector:
        pairs.append((entry.projector, entry.projector_sha256))
    if decision and any(not recorded for _, recorded in pairs):
        return EntryOutcome(
            entry.model,
            "failed",
            "model-invalid",
            "A decision model needs a recorded SHA-256 for each file.",
        )
    for path, recorded in pairs:
        if recorded and hashes.sha256(path) != recorded.lower():
            return _failed(entry, "file-changed", os.path.basename(path))
    return None


def plan_entry(entry: EntryLike, *, decision: bool, hashes: HashCache) -> EntryOutcome:
    """Check one entry and return its outcome (design D5 order).

    Order: name, file present, file rule, projector rule, preset, SHA-256.
    """
    if not entry.model or _INI_BREAK.search(entry.model) or entry.model != entry.model.strip():
        return _failed(entry, "model-invalid", "model name")
    if not (entry.file or "").strip():
        return EntryOutcome(entry.model, "not-downloaded")
    broken = _path_problem(entry.file or "", projector=False)
    if broken is None and entry.projector:
        broken = _path_problem(entry.projector, projector=True)
    if broken is not None:
        return _failed(entry, "model-invalid", broken)
    problems = preset_problems(dict(entry.preset or {}))
    if problems:
        return _failed(entry, "preset-invalid", problems[0].key)
    failed = _check_hashes(entry, decision, hashes)
    if failed is not None:
        return failed
    note = None if entry.sha256 else NOT_CHECKED_NOTE
    one_slot = (entry.preset or {}).get("parallel") == 1
    return EntryOutcome(
        entry.model, "listed", note=note, section=format_section(entry), one_slot=one_slot
    )


def plan_preset(
    entries: Iterable[EntryLike], *, decision_models: Collection[str] = (), hashes: HashCache
) -> PresetPlan:
    """Return the outcome of every entry, in list order.

    Args:
        entries: The ``llamacpp_models`` entries in force.
        decision_models: Model names a managed ``llamacpp`` decision entry
            names; such an entry needs a recorded SHA-256 for each file.
        hashes: The ``hashes.json`` cache of the router folder.
    """
    return PresetPlan(
        tuple(
            plan_entry(entry, decision=entry.model in decision_models, hashes=hashes)
            for entry in entries
        )
    )


# ── Sections in the file ────────────────────────────────────────────────


def join_sections(sections: Iterable[str]) -> str:
    """Join section texts with one blank line between them."""
    return "\n".join(sections)


def split_sections(text: str) -> dict[str, str]:
    """Return ``{section name: section text}`` of a file this module wrote.

    Each section text runs from its ``[name]`` line to the line before the
    blank line that ends it, ending in one newline, as :func:`format_section`
    returns it.
    """
    found: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("[") and line.endswith("]"):
            name, lines = line[1:-1], [line]
        elif name is not None and line == "":
            found[name] = "\n".join(lines) + "\n"
            name, lines = None, []
        elif name is not None:
            lines.append(line)
    return found


def replace_section(text: str, model: str, section: str | None) -> str:
    """Return *text* with the section of *model* replaced, added or (``None``) removed.

    Every other section stays byte-identical, so the router reload keeps
    its model loaded (spike 1.2).
    """
    sections = split_sections(text)
    if section is None:
        sections.pop(model, None)
    else:
        sections[model] = section
    return join_sections(sections.values())


def write_preset(folder: Path, text: str) -> Path:
    """Write *text* to ``<folder>/models.ini`` through a temporary file and a rename."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / PRESET_FILE
    temporary = folder / f"{PRESET_FILE}.tmp"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, target)
    return target


def read_preset(folder: Path) -> str:
    """Return the text of ``<folder>/models.ini``, ``""`` when it is missing."""
    try:
        return (folder / PRESET_FILE).read_text(encoding="utf-8")
    except OSError:
        return ""
