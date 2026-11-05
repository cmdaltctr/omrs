"""Lazy registry of decision model kinds (design D2, root invariant 11).

Maps a kind to its adapter module path. ``get()`` imports the module on first
use. Adding a kind is one new file plus one ``register()`` line at the bottom.
Only ``compose_decision`` and this package may use the adapters (import-linter
contract ``providers-constructed-only-in-compose``).

An adapter module defines ``build_request``, ``read_reply``,
``reported_model``, ``NOT_YET_TESTED`` and ``LOCAL_RUNTIME``.
"""

from __future__ import annotations

import importlib
from types import ModuleType

_registry: dict[str, str] = {}
_cache: dict[str, ModuleType] = {}


def register(kind: str, module_path: str) -> None:
    """Register decision model *kind*, served by the adapter at *module_path*."""
    _registry[kind] = module_path


def get(kind: str) -> ModuleType:
    """Return the adapter module of *kind*.

    Raises:
        KeyError: *kind* is not registered. The message names the registered kinds.
    """
    if kind in _cache:
        return _cache[kind]
    if kind not in _registry:
        raise KeyError(f"Unknown decision model kind {kind!r}. Registered: {kinds()}")
    module = importlib.import_module(_registry[kind])
    _cache[kind] = module
    return module


def kinds() -> list[str]:
    """Return the sorted registered kinds."""
    return sorted(_registry)


def not_yet_tested() -> list[str]:
    """Return the sorted kinds with no recorded live request ("Not yet tested")."""
    return [kind for kind in kinds() if getattr(get(kind), "NOT_YET_TESTED", True)]


# ── Built-in kinds ──────────────────────────────────────────────────────
register("llamacpp", "omrs.core.providers.decision.llamacpp")
register("typesafe", "omrs.core.providers.decision.typesafe")
register("cloudflare", "omrs.core.providers.decision.cloudflare")
register("ollama", "omrs.core.providers.decision.ollama")
