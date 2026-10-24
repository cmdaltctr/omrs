"""What an uninstall from the app removes, and when it is refused (design D1, D2, D4).

D1, the packages to remove: the names of the extra's own requirements that
are installed, without any name that a base requirement of ``omrs`` names,
that another installed extra lists, or that any other installed distribution
requires. The reverse map reads each ``Requires-Dist`` name without its
marker, so a marker never removes an edge. ``omrs`` itself is not a requirer
here (its extras are handled by the two rules before). A package that only a
package being removed requires still counts as required, so it is kept.
``uv pip uninstall`` leaves orphans; the lasting command drops them.

D2, the in-use map: the setting values that select each extra. Both the
frozen ``EffectiveSettings`` and the saved ``omrs.jsonc`` count, because the
next launch reads the saved value.

This module only reads metadata and ``omrs.jsonc``; it starts no process.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from importlib import metadata
from typing import Any

from ...config.settings_file import read_settings_file
from .install_environment import (
    _EXTRA_CLAUSE,
    EXCLUDED_EXTRAS,
    UV_TOOL,
    InstallEnvironment,
    _requirement_name,
    extra_requirements,
    tool_install_command,
)

#: Installed distribution name to the names it requires (markers ignored).
Installed = Mapping[str, frozenset[str]]

#: Extra to the ``(setting key, value)`` pairs that select it, checked in order.
#: An empty tuple means no setting selects the extra (``hybrid``: the built-in
#: BM25 takes over). Keys are ``omrs.jsonc`` keys and ``EffectiveSettings`` paths.
IN_USE: dict[str, tuple[tuple[str, str], ...]] = {
    "chroma": (("vector_store", "chroma"),),
    "torch": (("retrieval.rerank_backend", "torch"),),
    "pdf-pypdfium2": (("pdf_reader", "pypdfium2"),),
    "azure": (("document_backend", "azure"),),
    "community-leiden": (("community_algorithm", "leiden"),),
    "anthropic": (("answer.provider", "anthropic"), ("answer.verify_provider", "anthropic")),
    "hybrid": (),
}


def installed_requirements(distributions: Iterable[Any] | None = None) -> dict[str, frozenset[str]]:
    """Return every installed distribution with the names it requires.

    Args:
        distributions: Distributions to read. Defaults to
            ``importlib.metadata.distributions()``.
    """
    found: dict[str, set[str]] = {}
    for dist in metadata.distributions() if distributions is None else distributions:
        name = dist.metadata["Name"]
        if not name:
            continue
        names = found.setdefault(_requirement_name(name), set())
        names.update(_requirement_name(line) for line in dist.requires or [])
    return {name: frozenset(requires) for name, requires in found.items()}


def _omrs_requires() -> list[str]:
    try:
        return list(metadata.distribution("omrs").requires or [])
    except metadata.PackageNotFoundError:
        return []


def _extras(lines: list[str]) -> set[str]:
    """Return every extra name the requirement markers mention."""
    return {
        match["name"] for line in lines for match in _EXTRA_CLAUSE.finditer(line.partition(";")[2])
    }


def _installed_extra_names(extra: str, lines: list[str], installed: Installed) -> set[str]:
    """Return the requirement names of every other extra that is installed.

    An extra counts as installed when each requirement without another marker
    is installed. An extra with only conditional lines counts too (conservative).
    """
    names: set[str] = set()
    for other in _extras(lines) - {extra}:
        own = extra_requirements(other, lines)
        plain = [_requirement_name(line) for line in own if ";" not in line]
        if all(name in installed for name in plain):
            names.update(_requirement_name(line) for line in own)
    return names


def packages_to_remove(
    extra: str, installed: Installed, requires: Iterable[str] | None = None
) -> tuple[list[str], list[str]]:
    """Return the installed packages an uninstall of *extra* removes and keeps (D1).

    Args:
        extra: The extra name.
        installed: :func:`installed_requirements` or a test double.
        requires: The ``omrs`` requirement lines. Defaults to the installed metadata.

    Returns:
        ``(removes, keeps)``: normalised names, in requirement order.
    """
    lines = _omrs_requires() if requires is None else list(requires)
    own = dict.fromkeys(_requirement_name(line) for line in extra_requirements(extra, lines))
    base = {_requirement_name(line) for line in lines if "extra" not in line.partition(";")[2]}
    needed = base | _installed_extra_names(extra, lines, installed)
    removes: list[str] = []
    keeps: list[str] = []
    for name in (name for name in own if name in installed):
        required = any(
            name in names for dist, names in installed.items() if dist not in {name, "omrs"}
        )
        (keeps if required or name in needed else removes).append(name)
    return removes, keeps


def saved_settings() -> Mapping[str, Any]:
    """Return the valid values saved in ``omrs.jsonc``, by dotted key."""
    return read_settings_file().values


def _value(settings: Any, path: str) -> Any:
    for part in path.split("."):
        settings = getattr(settings, part, None)
    return settings


def _selects(value: Any, wanted: str) -> bool:
    return isinstance(value, str) and value.strip().lower() == wanted


def in_use_setting(extra: str, settings: Any, saved: Mapping[str, Any]) -> str | None:
    """Return the setting key that selects *extra*, or ``None`` (D2).

    Args:
        extra: The extra name.
        settings: The frozen ``EffectiveSettings``, or ``None``.
        saved: The values saved in ``omrs.jsonc``, by dotted key.
    """
    for path, wanted in IN_USE.get(extra, ()):
        effective = None if settings is None else _value(settings, path)
        if _selects(effective, wanted) or _selects(saved.get(path), wanted):
            return path
    return None


def uninstall_reason(
    extra: str | None,
    base: bool,
    availability: str,
    removes: Collection[str],
    setting: str | None,
    environment: InstallEnvironment,
    running: bool,
) -> str | None:
    """Return why *extra* cannot be uninstalled from the app now, or ``None``.

    The checks run in the order the contract fixes.

    Args:
        extra: The entry's extra, or ``None`` for an always-on integration.
        base: Whether the entry is part of every install.
        availability: The entry's availability in this launch.
        removes: The packages an uninstall would remove (D1).
        setting: The setting that selects the extra, or ``None``.
        environment: The detected install.
        running: Whether an install or uninstall job runs now.
    """
    if base or extra is None or extra in EXCLUDED_EXTRAS:
        return "not-uninstallable-here"
    if availability != "available":
        return "not-installed"
    # D1 can keep every package, for example torch: lancedb names both its
    # packages under lancedb's own extras. Never run an empty uninstall.
    if not removes:
        return "nothing-to-remove"
    if setting is not None:
        return "in-use"
    if environment.install_type != UV_TOOL:
        return "not-uv-tool"
    if environment.uv is None:
        return "uv-not-found"
    if running:
        return "install-running"
    return None


def lasting_uninstall_command(
    environment: InstallEnvironment, extra: str, *, base: bool
) -> str | None:
    """Return the reinstall command without *extra*, or ``None``.

    Only a ``uv tool`` receipt that lists *extra* gets one, and never a base
    entry or ``web``.

    Args:
        environment: The detected install.
        extra: The extra to drop.
        base: Whether the entry is part of every install.
    """
    if base or extra in EXCLUDED_EXTRAS or environment.install_type != UV_TOOL:
        return None
    if extra not in environment.receipt_extras:
        return None
    rest = [name for name in environment.receipt_extras if name != extra]
    return tool_install_command(environment, rest)
