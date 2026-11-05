"""Page writes of the router maps in ``omrs.jsonc`` (document-reading-routers, task 1.2).

:func:`write_map_entries` sets or deletes ``decision_models`` and
``document_routers`` entries through the safe writer of ``settings_file_write``:
one atomic replace, comments kept, the revision check. It refuses, and writes
nothing, when:

- a change does not name ``decision_models.<name>`` or ``document_routers.<name>``;
- an entry breaks a rule of ``settings_maps``, a literal key included;
- a deleted decision model is still named by a router after the change;
- a deleted (or renamed) router is named by a saved profile. The caller passes
  the profile check, because ``config/`` cannot read the workspace.

Only ``omrs web`` calls this. No message holds a value.

This module is a leaf: it imports only ``config/`` modules.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any

from .settings_file_write import SettingsFileRefused, WriteResult, commit_plan
from .settings_maps import (
    DECISION_MODELS,
    DOCUMENT_ROUTERS,
    ENTRY_RULE,
    MAP_KEYS,
    check_entry,
    entry_name_problem,
)
from .user_config import SECRETS_DIR, user_config_dir

#: Names the saved profiles that name a router. ``omrs web`` supplies it.
ProfilesNaming = Callable[[str], Collection[str]]

NOT_AN_ENTRY = (
    "This is not a decision model or router entry. "
    "Use decision_models.<name> or document_routers.<name>."
)
NO_PROFILE_CHECK = "A router can be deleted only after the saved profiles are checked."


def _split(key: str) -> tuple[str, str]:
    map_key, dot, name = key.partition(".")
    if map_key not in MAP_KEYS or not dot:
        raise SettingsFileRefused(f"{key}: {NOT_AN_ENTRY}")
    rule = entry_name_problem(map_key, name)
    if rule is not None:
        raise SettingsFileRefused(f"{key}: {rule}")
    return map_key, name


def _checked(key: str, map_key: str, value: Any, secrets: Path) -> dict[str, Any]:
    """Return the entry as the file will hold it, or refuse naming the broken field."""
    if not isinstance(value, Mapping):
        raise SettingsFileRefused(f"{key}: {ENTRY_RULE}")
    entry, problems = check_entry(map_key, value, secrets)
    if problems or entry is None:
        rules = "; ".join(f"{key}.{field}: {rule}" for _, field, rule in problems)
        raise SettingsFileRefused(rules)
    return entry.model_dump(exclude_none=True)


def _names(current: Mapping[str, Any], map_key: str) -> dict[str, Any]:
    found = current.get(map_key)
    return dict(found) if isinstance(found, Mapping) else {}


def _guard(
    plan: Mapping[str, Any], profiles_naming: ProfilesNaming | None
) -> Callable[[Mapping[str, Any]], None]:
    """Return the check that runs on the current file, under the write lock."""

    def guard(current: Mapping[str, Any]) -> None:
        routers = _names(current, DOCUMENT_ROUTERS)
        for key, value in plan.items():
            map_key, _, name = key.partition(".")
            if map_key != DOCUMENT_ROUTERS or value is not None or name not in routers:
                continue
            if current.get("document_router") == name:
                raise SettingsFileRefused(f"{key}: document_router names this router.")
            if profiles_naming is None:
                raise SettingsFileRefused(f"{key}: {NO_PROFILE_CHECK}")
            users = sorted(profiles_naming(name))
            if users:
                raise SettingsFileRefused(
                    f"{key}: the saved profile {', '.join(users)} names this router."
                )
            routers.pop(name)
        prefix = f"{DOCUMENT_ROUTERS}."
        routers.update(
            {k.removeprefix(prefix): v for k, v in plan.items() if k.startswith(prefix) and v}
        )
        for key, value in plan.items():
            map_key, _, name = key.partition(".")
            if map_key != DECISION_MODELS or value is not None:
                continue
            users = sorted(
                router
                for router, entry in routers.items()
                if isinstance(entry, Mapping) and entry.get("model") == name
            )
            if users:
                raise SettingsFileRefused(f"{key}: the router {', '.join(users)} names this model.")

    return guard


def write_map_entries(
    changes: Mapping[str, Mapping[str, Any] | None],
    *,
    revision: str | None,
    directory: Path | None = None,
    profiles_naming: ProfilesNaming | None = None,
) -> WriteResult:
    """Set or delete router map entries in ``omrs.jsonc``. All land in one replace, or none.

    A rename is a delete of the old name and a save of the new one in the same call.

    Args:
        changes: ``decision_models.<name>`` or ``document_routers.<name>`` to the
            entry's fields, or ``None`` to delete the entry.
        revision: The revision the caller read (``absent`` for no file). The
            write refuses when the file differs. ``None`` skips the check.
        directory: The user config folder (default: the resolved one).
        profiles_naming: Returns the saved profiles that name a router. A router
            delete is refused without it.

    Returns:
        The revision after the write.

    Raises:
        SettingsFileRefused: A change is not allowed (see the module text).
        SettingsFileConflict: The file changed or cannot be parsed.
        SettingsFileWriteError: The disk refused the write.
    """
    folder = directory or user_config_dir()
    plan: dict[str, Any] = {}
    for key, value in changes.items():
        map_key, _ = _split(key)
        plan[key] = None if value is None else _checked(key, map_key, value, folder / SECRETS_DIR)
    return commit_plan(folder, plan, revision, _guard(plan, profiles_naming))
