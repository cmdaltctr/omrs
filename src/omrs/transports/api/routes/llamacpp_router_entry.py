"""Merge and check one change to a router list entry (one-llamacpp-router, D3, D5; task 7.2).

A request changes some fields of one entry. :func:`merge_entry` lays the fields
that the request sent over the saved entry (``null`` removes a field), records the
SHA-256 of a new file, and checks the result against the entry rules, the managed
file rules, the duplicate rule and the role rules. A refusal is a
:class:`EntryRefused` with a plain line and an optional fixed reason; no line holds
a value.

Use this model (task 7.2) is one such request: ``model``, ``file`` and, from the
download status, ``sha256``. It sets no role setting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ....config.llamacpp_models import (
    DUPLICATE_RULE,
    PRESET_INVALID,
    REQUIRED_RULE,
    LlamaCppModelEntry,
    check_model_entry,
    file_problem,
)
from ....config.llamacpp_roles import ROLE_MISMATCH, derive_roles
from ....integrations.llamacpp_runtime.hashes import hash_file

#: The reasons of the role rules a save may break. Another role problem is not a save refusal.
_SAVE_REASONS = (ROLE_MISMATCH, PRESET_INVALID)


class EntryRefused(ValueError):
    """A change breaks a rule. ``str(error)`` is a plain line without any value.

    Attributes:
        reason: A fixed reason (``preset-key-unknown``, ``role-mismatch``,
            ``preset-invalid``) or ``None`` for a plain 400.
    """

    def __init__(self, message: str, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class EntryChange:
    """One request: the fields it sent (``None`` removes the field) and the mode in force."""

    sent: Mapping[str, Any]
    managed: bool


def _hash(path: str) -> str | None:
    """Return the SHA-256 of *path*, or ``None`` when it cannot be read."""
    try:
        return hash_file(path)
    except OSError:
        return None


def _problems(entry: dict[str, Any], change: EntryChange) -> None:
    """Raise :class:`EntryRefused` for the first broken entry rule."""
    if not entry.get("model"):
        raise EntryRefused(f"model: {REQUIRED_RULE}")
    found, problems = check_model_entry(entry)
    if problems or found is None:
        reason = next((p.reason for p in problems if p.reason), None)
        raise EntryRefused("; ".join(f"{p.field}: {p.rule}" for p in problems), reason)
    if change.managed:
        for name, projector in (("file", False), ("projector", True)):
            path = entry.get(name)
            rule = file_problem(path, projector=projector, exists=True) if path else None
            if rule is not None:
                raise EntryRefused(f"{name}: {rule}")


def merge_entry(
    entry_id: str,
    saved: Mapping[str, LlamaCppModelEntry],
    change: EntryChange,
    role_arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the entry as the list will hold it after *change*.

    Args:
        entry_id: The entry id.
        saved: The list in force.
        change: The fields the request sent.
        role_arguments: The ``derive_roles`` keywords of the role settings in force.

    Returns:
        The whole entry, without empty fields.

    Raises:
        EntryRefused: A rule is broken. Nothing is written.
    """
    current = saved.get(entry_id)
    entry: dict[str, Any] = {} if current is None else current.model_dump(exclude_none=True)
    for name, value in change.sent.items():
        if value is None:
            entry.pop(name, None)
        else:
            entry[name] = value.strip() if isinstance(value, str) else value
    _problems(entry, change)
    _record_hash(entry, current, change)
    others = [e.model for name, e in saved.items() if name != entry_id]
    if entry["model"] in others:
        raise EntryRefused(DUPLICATE_RULE)
    _check_roles(entry_id, saved, entry, role_arguments)
    return entry


def _record_hash(
    entry: dict[str, Any], current: LlamaCppModelEntry | None, change: EntryChange
) -> None:
    """Record the SHA-256 of a new file unless the request gave one (task 7.2)."""
    path = entry.get("file")
    if "sha256" in change.sent and change.sent["sha256"] is not None:
        return
    if not path:
        entry.pop("sha256", None)
        return
    if "file" in change.sent and (current is None or current.file != path):
        digest = _hash(path)
        if digest is None:
            entry.pop("sha256", None)  # unreadable here (an external router): nothing to record
        else:
            entry["sha256"] = digest


def _check_roles(
    entry_id: str,
    saved: Mapping[str, LlamaCppModelEntry],
    entry: dict[str, Any],
    role_arguments: Mapping[str, Any],
) -> None:
    """Refuse a change that gives a role to an entry that cannot serve it."""
    after_entry, _ = check_model_entry(entry)  # _problems accepted it
    if after_entry is None:
        return
    after = {**saved, entry_id: after_entry}
    known = {(p.role, p.reason) for p in derive_roles(saved, **role_arguments).problems}
    for problem in derive_roles(after, **role_arguments).problems:
        new = (problem.role, problem.reason) not in known
        if new and problem.reason in _SAVE_REASONS:
            raise EntryRefused(problem.rule, problem.reason)
