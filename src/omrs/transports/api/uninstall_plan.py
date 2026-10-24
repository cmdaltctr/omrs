"""What an uninstall from the app removes, and when it is refused (design D1, D2, D4).

D1, the packages to remove: the names of the extra's own requirements that
are installed, without any name that a base requirement of ``omrs`` names,
that another installed extra lists, or that any other installed distribution
requires. A ``Requires-Dist`` line behind its package's own extra
(``extra == "x"``) counts only when something asks for that extra, as
``pip check`` reads it; every other marker counts as true, so the check can
only keep too much. ``omrs`` itself is not a requirer here (its extras are
handled by the two rules before). Packages of the extra that only need each
other go together, as pip-autoremove removes them: the result is the largest
set of the extra's own packages that nothing outside the set requires.
``uv pip uninstall`` leaves orphans; the lasting command drops them.

D2, the in-use map: the setting values that select each extra. Both the
frozen ``EffectiveSettings`` and the saved ``omrs.jsonc`` count, because the
next launch reads the saved value.

This module only reads metadata and ``omrs.jsonc``; it starts no process.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from importlib import metadata
from typing import Any, NamedTuple

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


class Edge(NamedTuple):
    """One ``Requires-Dist`` line of an installed distribution.

    Attributes:
        name: The normalised name it requires.
        gate: The requiring package's own extras that switch the line on
            (``extra == "x"``); empty when the line always applies.
        asks: The extras of *name* the line asks for (``name[a,b]``).
    """

    name: str
    gate: frozenset[str] = frozenset()
    asks: frozenset[str] = frozenset()


#: Installed distribution name to its requirement lines. A plain name is an
#: :class:`Edge` that always applies (test doubles use that short form).
Installed = Mapping[str, frozenset[Edge] | frozenset[str]]

_ASKS = re.compile(r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*\[(?P<extras>[^\]]*)\]")
_OR = re.compile(r"\s+or\s+")

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


def _extra_name(name: str) -> str:
    """Normalise an extra name (PEP 685)."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def _gate(marker: str) -> frozenset[str]:
    """Return the extras that switch a marker on, or an empty set for always on.

    Every ``or`` part must name an ``extra ==`` clause; any other shape
    (``extra !=``, a part without an extra) counts as always on.
    """
    if "extra" not in marker:
        return frozenset()
    names: set[str] = set()
    for part in _OR.split(marker.strip().strip("()")):
        found = [match["name"] for match in _EXTRA_CLAUSE.finditer(part)]
        if not found or part.count("extra") != len(found):
            return frozenset()
        names.update(_extra_name(name) for name in found)
    return frozenset(names)


def _asks(spec: str) -> frozenset[str]:
    match = _ASKS.match(spec)
    if match is None:
        return frozenset()
    return frozenset(_extra_name(name) for name in match["extras"].split(",") if name.strip())


def _edge(line: str) -> Edge:
    spec, _, marker = line.partition(";")
    return Edge(_requirement_name(spec), _gate(marker), _asks(spec))


def installed_requirements(
    distributions: Iterable[Any] | None = None,
) -> dict[str, frozenset[Edge]]:
    """Return every installed distribution with its requirement lines.

    Args:
        distributions: Distributions to read. Defaults to
            ``importlib.metadata.distributions()``.
    """
    found: dict[str, set[Edge]] = {}
    for dist in metadata.distributions() if distributions is None else distributions:
        name = dist.metadata["Name"]
        if not name:
            continue
        found.setdefault(_requirement_name(name), set()).update(
            _edge(line) for line in dist.requires or []
        )
    return {name: frozenset(edges) for name, edges in found.items()}


def _edges(value: Iterable[Edge | str]) -> frozenset[Edge]:
    return frozenset(item if isinstance(item, Edge) else Edge(item) for item in value)


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


def _installed_extra_lines(extra: str, lines: list[str], installed: Installed) -> list[str]:
    """Return the requirement lines of every other extra that is installed.

    An extra counts as installed when each requirement without another marker
    is installed. An extra with only conditional lines counts too (conservative).
    """
    found: list[str] = []
    for other in _extras(lines) - {extra}:
        own = extra_requirements(other, lines)
        plain = [_requirement_name(line) for line in own if ";" not in line]
        if all(name in installed for name in plain):
            found.extend(own)
    return found


def _active(installed: Installed, omrs_lines: list[str]) -> dict[str, set[str]]:
    """Return each installed distribution with the names its active lines require.

    A gated line is active once something asks for one of its extras. The
    asked extras start from the active ``omrs`` lines and grow until nothing
    changes, because an asked extra can switch on a line that asks for more.
    """
    graph = {dist: _edges(edges) for dist, edges in installed.items() if dist != "omrs"}
    asked: defaultdict[str, set[str]] = defaultdict(set)
    for line in omrs_lines:
        edge = _edge(line)
        asked[edge.name] |= edge.asks
    changed = True
    while changed:
        changed = False
        for dist, edges in graph.items():
            for edge in edges:
                live = not edge.gate or bool(edge.gate & asked[dist])
                if live and not edge.asks <= asked[edge.name]:
                    asked[edge.name] |= edge.asks
                    changed = True
    return {
        dist: {edge.name for edge in edges if not edge.gate or edge.gate & asked[dist]}
        for dist, edges in graph.items()
    }


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
    base_lines = [line for line in lines if "extra" not in line.partition(";")[2]]
    other_lines = _installed_extra_lines(extra, lines, installed)
    needed = {_requirement_name(line) for line in base_lines + other_lines}
    present = [name for name in own if name in installed]
    active = _active(installed, base_lines + other_lines)
    # The largest set of the extra's packages that nothing outside it requires.
    removable = {name for name in present if name not in needed}
    changed = True
    while changed:
        changed = False
        for name in sorted(removable):
            if any(name in names for dist, names in active.items() if dist not in removable):
                removable.discard(name)
                changed = True
    removes = [name for name in present if name in removable]
    keeps = [name for name in present if name not in removable]
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
