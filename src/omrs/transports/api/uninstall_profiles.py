"""Saved user profiles in the uninstall in-use check (check-saved-profiles-before-uninstall).

ADR-096 checks the effective settings and the saved ``omrs.jsonc``
(:func:`uninstall_plan.in_use_setting`). A user profile can also select an
extra, in two ways only:

* an enabled ``read.document`` step in its ingest graph names a PDF reader,
  through ``params.pdf_reader``;
* its ``embed_provider`` names a provider whose embedding registry entry
  declares an extra.

No other node parameter names an extra: the LLM providers, the vector store
and the reranker backend are host-owned (``core/pipelines/levers.py``).
Built-in profiles run on host settings, so the global check covers them.

The walk reads only the current revision of each profile that is not
deleted. It starts no process and writes nothing. When the profiles cannot be
read, it logs a warning and the global check alone decides.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple

from ...core.providers.embeddings import registry as embedding_registry
from .uninstall_plan import IN_USE, in_use_setting

logger = logging.getLogger(__name__)

#: Node operations whose parameters can name an extra. Extend this, and the
#: walk below, when a new node parameter selects an optional package.
PROFILE_READER_OPERATIONS: frozenset[str] = frozenset({"read.document"})


class InUse(NamedTuple):
    """Why an extra is in use.

    Attributes:
        setting: The setting key (``omrs.jsonc`` key, or the key inside the profile).
        profile: ``{"id", "title"}`` of the profile that uses the extra, or
            ``None`` when a global setting does.
    """

    setting: str
    profile: dict[str, str] | None = None


def _readers(extra: str) -> frozenset[str]:
    """Return the ``pdf_reader`` values that select *extra* (from :data:`IN_USE`)."""
    return frozenset(value for key, value in IN_USE.get(extra, ()) if key == "pdf_reader")


def _graph_readers(document: Mapping[str, Any] | None) -> Iterator[str]:
    """Yield the PDF reader of every enabled Read document step in a graph."""
    for node in (document or {}).get("nodes", []):
        if node.get("operation") not in PROFILE_READER_OPERATIONS or node.get("enabled") is False:
            continue
        reader = (node.get("params") or {}).get("pdf_reader")
        if isinstance(reader, str):
            yield reader.strip().lower()


def profile_in_use(extra: str, catalogue: Any) -> InUse | None:
    """Return the first user profile that selects *extra*, or ``None``.

    Args:
        extra: The extra name.
        catalogue: A ``ProfileCatalogue`` (``list_profiles``, ``slot_document``),
            or ``None`` when the server has no workspace.
    """
    if catalogue is None:
        return None
    readers = _readers(extra)
    try:
        for record in catalogue.list_profiles():
            who = {"id": str(record["profile_id"]), "title": str(record.get("title") or "")}
            if readers and readers & set(
                _graph_readers(catalogue.slot_document(record["profile_id"], "ingest"))
            ):
                return InUse("pdf_reader", who)
            provider = record.get("embed_provider")
            if isinstance(provider, str) and embedding_registry.extra_for(provider) == extra:
                return InUse("embed_provider", who)
    except Exception:
        # The detail stays out of the message; the stack goes to the redacted log.
        logger.warning("Could not read the saved profiles for the uninstall check.", exc_info=False)
        logger.debug("Profile read failed.", exc_info=True)
    return None


def in_use(extra: str, settings: Any, saved: Mapping[str, Any], catalogue: Any) -> InUse | None:
    """Return why *extra* is in use: a global setting first, then a user profile.

    Args:
        extra: The extra name.
        settings: The frozen ``EffectiveSettings``, or ``None``.
        saved: The values saved in ``omrs.jsonc``, by dotted key.
        catalogue: The profile catalogue, or ``None``.
    """
    setting = in_use_setting(extra, settings, saved)
    if setting is not None:
        return InUse(setting)
    return profile_in_use(extra, catalogue)
