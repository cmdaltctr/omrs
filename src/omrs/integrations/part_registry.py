"""Shared registry helper for page-reading parts.

One :class:`PartRegistry` holds the lazy registrations of one kind of part
(PDF readers, local OCR backends, page rules). Registering a part stores an
import string and a dictionary of declared facts. Nothing imports until
:meth:`PartRegistry.get` or :meth:`PartRegistry.probe` runs.

This module imports no part and nothing from ``omrs.core`` (contract
``integrations-are-leaves``). It uses the standard library only.
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import threading
from typing import Any


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
