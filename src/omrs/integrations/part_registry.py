"""Shared registry helper for page-reading parts.

One :class:`PartRegistry` holds the lazy registrations of one kind of part
(PDF readers, local OCR backends, page rules). Registering a part stores an
import string and a dictionary of declared facts. Nothing imports until
:meth:`PartRegistry.get` or :meth:`PartRegistry.probe` runs.

It also holds entry-point discovery (change local-ocr-backends, design D11):
:func:`discover_parts` reads the groups in :data:`GROUPS` once per process,
loads each named descriptor (never the implementation) and registers each
accepted part in the registry of its kind.

This module imports no part and nothing from ``omrs.core`` (contract
``integrations-are-leaves``). It uses the standard library only. The
composition root passes the descriptor classes in.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import importlib.util
import logging
import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any

logger = logging.getLogger(__name__)


class PartRegistry:
    """Lazy registry of named parts with a per-process switch-off.

    Args:
        label: Human name of the part kind, for example ``"PDF reader"``.
            It appears in every error message.
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._entries: dict[str, dict[str, Any]] = {}
        self._cache: dict[str, Any] = {}
        self._off: dict[str, str] = {}
        self._lock = threading.RLock()

    @property
    def cache(self) -> dict[str, Any]:
        """The live cache of loaded part objects (same dict on every call)."""
        return self._cache

    def register(
        self,
        name: str,
        import_path: str,
        *,
        probe_module: str | None = None,
        **facts: Any,
    ) -> None:
        """Register a part. Registering a name again replaces it.

        Args:
            name: Registry key.
            import_path: ``"module:attr"`` string. It is not imported here.
            probe_module: Module that must be importable for the part to
                work. Defaults to the module part of ``import_path``.
            **facts: Declared facts the caller reads back with
                :meth:`describe`.
        """
        with self._lock:
            self._entries[name] = {
                "import_path": import_path,
                "probe_module": probe_module or import_path.split(":", maxsplit=1)[0],
                **facts,
            }
            self._cache.pop(name, None)

    def _require(self, name: str) -> dict[str, Any]:
        """Return the entry for *name* or raise ``KeyError`` naming the choices."""
        try:
            return self._entries[name]
        except KeyError:
            raise KeyError(
                f"Unknown {self._label} {name!r}. Available: {sorted(self._entries)}"
            ) from None

    def describe(self, name: str) -> dict[str, Any]:
        """Return a fresh dict of the import path, probe module and facts.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            return dict(self._require(name))

    def names(self) -> list[str]:
        """Return the registered names, sorted."""
        with self._lock:
            return sorted(self._entries)

    def get(self, name: str) -> Any:
        """Import the part on first call and return the cached attribute object.

        Raises:
            KeyError: If *name* is not registered.
            ImportError: If the part module cannot be imported.
        """
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            entry = self._require(name)
            module_path, attr = entry["import_path"].split(":")
            try:
                module = importlib.import_module(module_path)
            except ImportError as exc:
                raise ImportError(
                    f"{self._label} {name!r} could not be imported (module {module_path!r}): {exc}"
                ) from exc
            part = getattr(module, attr)
            self._cache[name] = part
            return part

    def probe(self, name: str) -> None:
        """Import the probe module of *name*.

        Raises:
            KeyError: If *name* is not registered.
            ImportError: If the probe module cannot be imported.
        """
        with self._lock:
            module_name = self._require(name)["probe_module"]
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(
                f"{self._label} {name!r} dependency {module_name!r} is not importable: {exc}"
            ) from exc

    def installed(self, name: str) -> bool:
        """Report whether the probe module can be found, without importing it.

        A dotted probe name makes Python import its parent packages, so the
        built-in parts use top-level probe modules.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            module_name = self._require(name)["probe_module"]
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ModuleNotFoundError, ValueError):
            return False

    def switch_off(self, name: str, reason: str) -> None:
        """Switch the part off for this process and record why.

        Raises:
            KeyError: If *name* is not registered.
        """
        with self._lock:
            self._require(name)
            self._off[name] = reason

    def off_reason(self, name: str) -> str | None:
        """Return the switch-off reason for *name*, or ``None`` when it is on."""
        with self._lock:
            return self._off.get(name)

    def reset_off(self) -> None:
        """Clear every switch-off reason (test seam)."""
        with self._lock:
            self._off.clear()

    def snapshot(self) -> object:
        """Return an opaque copy of all state (test seam)."""
        with self._lock:
            return (
                copy.deepcopy(self._entries),
                dict(self._cache),
                dict(self._off),
            )

    def restore(self, state: object) -> None:
        """Put back state taken by :meth:`snapshot` (test seam).

        The cache dict keeps its identity, so holders of :attr:`cache` stay
        valid.
        """
        entries, cache, off = state  # type: ignore[misc]
        with self._lock:
            self._entries = copy.deepcopy(entries)
            self._cache.clear()
            self._cache.update(cache)
            self._off = dict(off)


# ── Entry-point discovery (design D11) ───────────────────────────────────

#: Entry-point group to part kind. The kinds equal the ``KIND_*`` values of
#: ``core/reading_parts.py``, which this module cannot import.
GROUPS: dict[str, str] = {
    "omrs.pdf_readers": "pdf_reader",
    "omrs.local_ocr_backends": "local_ocr_backend",
    "omrs.page_rules": "page_rule",
}


@dataclass(frozen=True)
class DiscoveredPart:
    """One entry point of a reading-part group, accepted or not.

    Attributes:
        name: Descriptor name, or ``None`` when the descriptor could not load.
        kind: ``pdf_reader``, ``local_ocr_backend`` or ``page_rule``.
        group: The entry-point group.
        distribution: The distribution that declares the entry point.
        version: The version of that distribution.
        value: The entry-point value, ``module:attr``.
        descriptor: The loaded descriptor when it was accepted, else ``None``.
            Its ``source`` is the distribution name.
        problem: Why the part was refused or is broken, else ``None``.
    """

    name: str | None
    kind: str
    group: str
    distribution: str | None
    version: str | None
    value: str
    descriptor: object | None
    problem: str | None


def _register_reader(descriptor: Any, source: str) -> None:
    from .pdf import registry

    registry.register(
        descriptor.name,
        descriptor.import_path,
        descriptor.probe_module,
        text_format=descriptor.text_format,
        page_provenance=descriptor.page_provenance,
        output_revision=descriptor.output_revision,
    )


def _register_backend(descriptor: Any, source: str) -> None:
    from .pdf.local_ocr import registry

    registry.register(
        descriptor.name,
        descriptor.import_path,
        producer=descriptor.producer,
        min_confidence=descriptor.min_confidence,
        calibrated_by=descriptor.calibrated_by,
        keeps_scripts=descriptor.keeps_scripts,
        probe_module=descriptor.probe_module,
    )


def _register_rule(descriptor: Any, source: str) -> None:
    from .pdf.page_rules import registry

    registry.register(
        descriptor.name,
        descriptor.import_path,
        order=descriptor.order,
        drops_pages=descriptor.drops_pages,
        sends_direct=descriptor.sends_direct,
        has_post_check=descriptor.has_post_check,
        has_degrade=descriptor.has_degrade,
        source=source,
    )


#: Part kind to the function that registers an accepted descriptor of that kind.
_REGISTER: dict[str, Callable[[Any, str], None]] = {
    "pdf_reader": _register_reader,
    "local_ocr_backend": _register_backend,
    "page_rule": _register_rule,
}

_discovery_lock = threading.Lock()
_discovered: tuple[DiscoveredPart, ...] | None = None


def _accept(
    entry: EntryPoint,
    kind: str,
    builtin: Collection[str],
    expected: type,
    taken: dict[tuple[str, str], str],
) -> tuple[str | None, object | None, str | None]:
    """Load one descriptor and return ``(name, descriptor, problem)``."""
    source = entry.dist.name if entry.dist is not None else entry.value
    try:
        loaded = entry.load()
    except Exception as exc:  # noqa: BLE001 - an external part never stops start-up
        return None, None, f"it could not be loaded ({type(exc).__name__}: {exc})"
    name = getattr(loaded, "name", None)
    name = name if isinstance(name, str) else None
    if not isinstance(loaded, expected):
        return name, None, f"it is a {type(loaded).__name__}, not a {expected.__name__}"
    if name in builtin:
        return name, None, f"the name {name!r} belongs to a built-in {kind}; the built-in stays"
    if (kind, name) in taken:
        return name, None, f"the name {name!r} is already taken by {taken[(kind, name)]!r}"
    descriptor = dataclasses.replace(loaded, source=source)  # type: ignore[type-var]
    _REGISTER[kind](descriptor, source)
    taken[(kind, name)] = source
    return name, descriptor, None


def _discover(
    builtin_names: Mapping[str, Collection[str]], descriptor_types: Mapping[str, type]
) -> tuple[DiscoveredPart, ...]:
    found: list[DiscoveredPart] = []
    taken: dict[tuple[str, str], str] = {}
    for group, kind in GROUPS.items():
        for entry in entry_points(group=group):
            builtin, expected = builtin_names.get(kind, ()), descriptor_types[kind]
            try:
                name, descriptor, problem = _accept(entry, kind, builtin, expected, taken)
            except Exception as exc:  # noqa: BLE001 - an external part never stops start-up
                name, descriptor, problem = None, None, f"{type(exc).__name__}: {exc}"
            dist = entry.dist
            part = DiscoveredPart(
                name=name,
                kind=kind,
                group=group,
                distribution=dist.name if dist is not None else None,
                version=dist.version if dist is not None else None,
                value=entry.value,
                descriptor=descriptor,
                problem=problem,
            )
            if problem is not None:
                logger.warning(
                    "Reading part %s (%s, entry point %r) from distribution %r was refused: %s.",
                    repr(name) if name else entry.name,
                    kind,
                    entry.value,
                    part.distribution,
                    problem,
                )
            found.append(part)
    return tuple(found)


def _log_found(found: tuple[DiscoveredPart, ...]) -> None:
    """Write the one start-up line that names the discovered parts."""
    if not found:
        return
    accepted = [
        f"{part.name} ({part.kind} from {part.distribution} {part.version})"
        for part in found
        if part.descriptor is not None
    ]
    refused = len(found) - len(accepted)
    logger.info(
        "Discovered reading parts: %s; refused or broken: %d.",
        ", ".join(accepted) or "none",
        refused,
    )


def discover_parts(
    *,
    builtin_names: Mapping[str, Collection[str]],
    descriptor_types: Mapping[str, type],
) -> tuple[DiscoveredPart, ...]:
    """Read the reading-part entry-point groups, once per process.

    Each entry point names a descriptor. Discovery loads the descriptor module
    only; the implementation loads on first use through ``import_path``. An
    accepted part is registered in the registry of its kind. A descriptor of
    the wrong type, or with a name a built-in or an earlier distribution
    holds, is refused with one warning. A descriptor that fails to load is
    listed with its problem. Start-up never fails because of an external part.

    Args:
        builtin_names: Part kind to the names of its built-in parts.
        descriptor_types: Part kind to the descriptor class it must be.

    Returns:
        Every entry point found, in group order. Later calls return the
        same tuple without reading the groups again.
    """
    global _discovered
    with _discovery_lock:
        if _discovered is None:
            _discovered = _discover(builtin_names, descriptor_types)
            _log_found(_discovered)
        return _discovered


def discovered_parts() -> tuple[DiscoveredPart, ...]:
    """Return what discovery found, or ``()`` when it never ran. Never runs it."""
    return _discovered or ()


def reset_discovery() -> None:
    """Forget the discovery result, so the next call reads the groups again (test seam).

    The registrations of accepted parts stay; tests restore the registries
    with :meth:`PartRegistry.restore`.
    """
    global _discovered
    with _discovery_lock:
        _discovered = None
