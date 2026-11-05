"""Store a source whose router failed during the read as not runnable (design D9).

Change document-reading-routers, review finding 4. The index identity of a
source is computed before the read, and its ``document_router`` entry holds
``runnable``. A router server can stop between that step and the read. The
read then stamps ``router_status`` with a reason and leaves pages unjudged.
Stored under the ``runnable: true`` identity, the source would read as
current for good. So:

- :func:`unrouted_index_identity` computes, next to the identity, the digest
  the same source gets with ``runnable: false`` (only when a router is
  selected and the two differ).
- :func:`settle_router_identity` swaps that digest in, with its source
  version, when a chunk of the read carries a ``router_status`` other than
  ``ok``. Both ingest paths call it after the read and before the vectors
  are stamped, so the next explicit ingest that can judge the pages reads
  the source again.

``ocr_identity`` reads :func:`router_assumed_not_runnable`; this module adds
nothing to ``source_state``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .source_state import build_source_version

if TYPE_CHECKING:
    from .sources import SourceIdentity

#: The router status of a read whose router judged as asked (the rule's ``ok``).
_ROUTER_OK = "ok"
_NOT_RUNNABLE: ContextVar[bool] = ContextVar("omrs_router_not_runnable", default=False)


def router_assumed_not_runnable() -> bool:
    """Return whether the identity being built must record ``runnable: false``."""
    return _NOT_RUNNABLE.get()


@contextmanager
def _assume_router_not_runnable() -> Iterator[None]:
    token = _NOT_RUNNABLE.set(True)
    try:
        yield
    finally:
        _NOT_RUNNABLE.reset(token)


def unrouted_index_identity(
    settings: Any, build: Callable[[], str], index_identity: str
) -> str | None:
    """Return the digest of the source with ``runnable: false``, or ``None``.

    Args:
        settings: The settings the identity was built with.
        build: Builds the identity digest again with the same inputs.
        index_identity: The digest built with the router's real state.

    Returns:
        ``None`` with no router selected, or when the router could not run
        already (the two digests are equal), else the other digest.
    """
    name = (getattr(settings, "document_router", "") or "").strip()
    if name in ("", "none"):
        return None
    with _assume_router_not_runnable():
        other = build()
    return None if other == index_identity else other


def router_failed(nodes: Iterable[Any]) -> bool:
    """Return whether a chunk of the read carries a ``router_status`` other than ``ok``."""
    for node in nodes:
        status = (getattr(node, "metadata", None) or {}).get("router_status")
        if status is not None and status != _ROUTER_OK:
            return True
    return False


def settle_router_identity(identity: SourceIdentity, nodes: Iterable[Any]) -> SourceIdentity:
    """Return *identity*, or its ``runnable: false`` form when the read's router failed.

    Args:
        identity: A ``SourceIdentity`` from ``prepare_source``.
        nodes: The chunks of the read.
    """
    unrouted = identity.unrouted_identity
    if unrouted is None or not router_failed(nodes):
        return identity
    return replace(
        identity,
        index_identity=unrouted,
        source_version=build_source_version(identity.content_hash, unrouted),
        unrouted_identity=None,
    )
