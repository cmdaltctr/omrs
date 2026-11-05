"""Canonical OCR identity payload builders (task 2.13, design D8).

Two small pure builders produce the OCR corner of the
``source_index_identity`` payload. They live beside
``core/ingestion/source_state.py`` rather than inside it because that
module sits at the 500-line ceiling; ``source_state`` imports them the
same way ``compose`` re-imports from ``capabilities`` when the natural
home is full.

Design D8 contract implemented here:

- the OCR routing switch (``enabled``) enters the payload as resolved
  data, never re-read from the environment;
- the identity carries what changes the emitted text — the routing unit
  and the local tier's escalation threshold — and not where files live or
  how they are fetched. A model directory is a filesystem location, so the
  same model under a different path would reindex for nothing. Offline
  mode decides whether a download may happen; its only route to different
  text is whether the model resolves, which the resolved model identity
  records directly (change page-level-ocr-routing, task 4.2);
- the routing unit, the blank-test version and the local tier are
  present for every source: ``page`` is the only unit (change
  page-routing-default, schema 7). ``local_tier.model`` joins only with a
  resolved identity. Absence means unresolved, which is itself
  identity-relevant: the runtime appearing changes the emitted text, so
  the digest moves then and only then;
- the resolved worker fingerprint enters as ONE canonical,
  transient-free payload. An unavailable worker contributes the stable
  ``UNAVAILABLE_OCR_WORKER_FINGERPRINT`` shape — the field is never
  omitted and never carries process identifiers, timestamps, or host
  paths;
- no second identity mechanism and no hashing outside
  ``build_index_identity``: these builders return plain JSON-ready
  dictionaries and the single sha256 stays in ``source_state``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .. import reading_parts
from ..reading_parts import (
    DEFAULT_LOCAL_OCR_BACKENDS,
    KIND_LOCAL_OCR_BACKEND,
    broken,
    effective_cut,
    local_backend,
)

#: The canonical unavailable fingerprint payload. Byte-identical, by
#: construction, to ``asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)`` from
#: ``integrations/ocr_worker/fingerprint.py``: every identity field
#: empty and ``available=False``. Duplicated here only so this leaf
#: module does not import the worker implementation; the re-ingestion
#: tests pin the no-drift equality.
_UNAVAILABLE_FINGERPRINT_PAYLOAD: dict[str, Any] = {
    "available": False,
    "protocol_version": "",
    "packages": (),
    "pipeline_identity": "",
    "pipeline_revision": "",
    "model_identity": "",
    "model_revision": "",
    "output_schema_id": "",
    "output_schema_version": "",
    "backend_id": "",
}


def ocr_routing_payload(
    settings: Any, *, local_model_identity: str | None = None
) -> dict[str, Any]:
    """Return the canonical OCR routing payload from settings.

    Args:
        settings: Settings object (flat ``Settings`` or frozen
            ``EffectiveSettings``) carrying ``ocr_fallback_enabled``,
            ``ocr_routing_unit`` and ``ocr_local_min_confidence``.
        local_model_identity: The local OCR tier's resolved model
            identity (``name@revision``), or ``None`` when unresolved.

    Returns:
        A JSON-ready dict: the routing switch, the routing unit, the
        blank-test version and the local tier's escalation threshold,
        plus the local model identity when resolved. The operational
        worker settings (folder, timeout) are deliberately absent: they
        shape dispatch, never chunk text.
    """
    # The blank-test version (skip-blank-pages-before-worker): the threshold
    # decides which flagged pages emit no document at all, so a version bump
    # must reindex. Imported at call time so a test can move the version and
    # see the digest follow, the same seam as the maths detector version.
    from ...integrations.pdf.blank_pages import BLANK_PAGE_TEST_VERSION

    # Design D9: the effective cut of the default backend, so an unset override
    # and an explicit 0.9 give the same bytes. The list enters ``parser``.
    local_tier: dict[str, Any] = {
        "min_confidence": effective_cut(settings, DEFAULT_LOCAL_OCR_BACKENDS[0])
    }
    # The resolved model identity (task 4.2): absent while unresolved,
    # present once the runtime resolves it. The digest moves with this key,
    # which is correct: the model changes what the pages read as.
    if local_model_identity is not None:
        local_tier["model"] = local_model_identity
    return {
        "enabled": settings.ocr_fallback_enabled,
        "routing_unit": settings.ocr_routing_unit,
        "blank_page_test": BLANK_PAGE_TEST_VERSION,
        "local_tier": local_tier,
    }


def resolved_routing_payload(settings: Any) -> dict[str, Any]:
    """Build the routing payload with the resolved local model identity.

    Boundary wrapper for the composition path: resolves the local tier's
    model identity exactly once per process (the probe is cached), then
    delegates to :func:`ocr_routing_payload`. The probe runs only when the
    OCR fallback is enabled and ``ocr_local_backends`` holds the default
    backend. Otherwise that model cannot change the emitted text, so the
    payload leaves it out.

    The lazy import keeps pdf-inspector out of every import of this
    module; ``core`` reaching into ``integrations`` lazily inside a
    function follows the ``codebase_map`` → ``integrations.magika``
    precedent.

    Args:
        settings: Settings object carrying the routing switch, the routing
            unit and the local tier settings.

    Returns:
        The canonical routing payload, with ``local_tier.model`` when the
        probe resolved an identity.
    """
    local_model_identity = None
    # The default backend's model counts only when the list holds it (PR #168, finding 5).
    listed = tuple(getattr(settings, "ocr_local_backends", DEFAULT_LOCAL_OCR_BACKENDS))
    if getattr(settings, "ocr_fallback_enabled", False) and DEFAULT_LOCAL_OCR_BACKENDS[0] in listed:
        from ...integrations.pdf.page_routing import resolve_local_model_identity

        local_model_identity = resolve_local_model_identity(settings)
    return ocr_routing_payload(settings, local_model_identity=local_model_identity)


def local_backends_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of a non-default local OCR list (design D9, D10).

    The default list adds nothing, so every digest stays put. Another list
    names each backend in list order with its effective cut, its kept scripts
    (a sorted list, or ``None``) and its model once resolved, plus the
    output-script classifier version. A model is resolved only when OCR
    routing is on, the rule :func:`resolved_routing_payload` follows. PDF
    sources only: :func:`omrs.core.ingestion.reader_identity.pdf_parser_payload`
    calls it, so other sources keep their digest.

    Args:
        settings: Settings carrying ``ocr_local_backends``,
            ``ocr_local_min_confidence`` and ``ocr_fallback_enabled``.

    Returns:
        ``{}`` for the default list, else ``{"local_ocr_backends": {...}}``.
    """
    names = tuple(getattr(settings, "ocr_local_backends", DEFAULT_LOCAL_OCR_BACKENDS))
    if names == DEFAULT_LOCAL_OCR_BACKENDS:
        return {}
    # A broken discovered backend reads no page, so it adds nothing (finding 4).
    off = broken(KIND_LOCAL_OCR_BACKEND)
    names = tuple(name for name in names if name not in off)
    # Call-time imports: the same lazy seam as resolved_routing_payload.
    from ...integrations.pdf import page_routing, script_routing

    resolve = getattr(settings, "ocr_fallback_enabled", False)
    backends: list[dict[str, Any]] = []
    for name in names:
        kept = local_backend(name).keeps_scripts
        entry: dict[str, Any] = {"name": name, "min_confidence": effective_cut(settings, name)}
        model = (
            page_routing.resolve_local_model_identity(settings, backend=name) if resolve else None
        )
        if model is not None:
            entry["model"] = model
        entry["keeps_scripts"] = sorted(kept) if kept is not None else None
        backends.append(entry)
    return {
        "local_ocr_backends": {
            "backends": backends,
            "output_script_version": script_routing.OUTPUT_SCRIPT_VERSION,
        }
    }


def ocr_fingerprint_payload(fingerprint: Any) -> dict[str, Any]:
    """Return the canonical transient-free payload of a resolved fingerprint.

    Args:
        fingerprint: The resolved :class:`OcrWorkerFingerprint` (any
            frozen dataclass with its field set), or ``None`` when no
            fingerprint was supplied.

    Returns:
        ``asdict(fingerprint)`` for a dataclass — the canonical shape
        carries availability, protocol version, package
        name/version pairs, pipeline and model identities and
        revisions, and the output-schema identity and version. Any
        other input (including ``None``) yields the stable unavailable
        payload, so a missing fingerprint can never silently omit the
        field from the index identity.
    """
    if is_dataclass(fingerprint) and not isinstance(fingerprint, type):
        return asdict(fingerprint)
    return dict(_UNAVAILABLE_FINGERPRINT_PAYLOAD)


def route_fingerprints(ocr_client: Any) -> tuple[Any, Any]:
    """Return the ``(primary, fallback)`` fingerprints of the injected routes.

    Change modular-ocr-workers-dots-mocr, design D7: the existing
    ``ocr_worker_fingerprint`` is the first route's, and
    ``ocr_fallback_fingerprint`` is the second's. Later routes are read by
    :func:`more_route_fingerprints`. A single injected
    client is a primary-only route pair; ``None`` (OCR off) and a
    missing route yield ``None``, which
    :func:`ocr_fingerprint_payload` maps to the stable unavailable payload.

    Args:
        ocr_client: The injected ``OcrRoutes``, one managed client, or
            ``None``.

    Returns:
        The primary and fallback fingerprints (either may be ``None``).
    """
    if ocr_client is None:
        return None, None
    primary = getattr(ocr_client, "fingerprint", None)
    return primary, getattr(ocr_client, "fallback_fingerprint", None)


def more_route_fingerprints(ocr_client: Any) -> tuple[Any, ...]:
    """Return the fingerprints of the third and later routes, in list order.

    Change ordered-reader-and-ocr-lists, design D5. The first two routes keep
    their own identity keys, so a two-engine install (the default) has none
    here and its digest does not move. A single client or ``None`` has none.
    """
    return tuple(getattr(ocr_client, "fingerprints", ())[2:])


def maths_routing_payload(settings: Any) -> dict[str, Any]:
    """Return the maths-routing identity block, present for every source.

    The resolved flag and the detector version decide which pages reach
    OCR, so each change re-ingests
    (spec maths-page-routing: "Maths routing SHALL participate in the
    source index identity").
    """
    from ...integrations.pdf.maths_pages import MATHS_DETECTOR_VERSION

    return {
        "enabled": bool(getattr(settings, "ocr_maths_routing_enabled", False)),
        "detector_version": MATHS_DETECTOR_VERSION,
    }


def non_latin_routing_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry for non-Latin routing, empty when the mode is ``off``.

    Change non-latin-script-routing. The mode and the detector version decide
    which flagged pages skip the local tier, so a change reindexes PDF sources.
    ``off`` adds nothing, so every digest from before the change stays the same.
    """
    mode = getattr(settings, "ocr_non_latin_routing", "off")
    if mode == "off":
        return {}
    from ...integrations.pdf.script_routing import SCRIPT_DETECTOR_VERSION

    return {"non_latin_routing": {"mode": mode, "detector_version": SCRIPT_DETECTOR_VERSION}}


def _entry_value(entry: Any, key: str, default: Any = None) -> Any:
    """Return *key* of a settings map entry given as a mapping or as an object."""
    if isinstance(entry, Mapping):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _decision_model_identity(entry: Any) -> dict[str, Any]:
    """Return the kind and model identity of a decision model entry (design D9).

    A managed entry adds the SHA-256 of its model and projector files. The
    address, the key and the file paths say where the model lives, not what
    it is, so they stay out.
    """
    if entry is None:
        return {}
    identity = {"kind": _entry_value(entry, "kind"), "model": _entry_value(entry, "model")}
    if _entry_value(entry, "server") == "managed":
        identity["model_sha256"] = _entry_value(entry, "model_sha256")
        identity["projector_sha256"] = _entry_value(entry, "projector_sha256")
    return identity


def document_router_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of the selected router, empty with no router.

    Change document-reading-routers, design D9. The entry holds what decides
    the text: the question, threshold, image flag, character limit, the
    decision model identity and the rule version. The router name, address,
    key and opt-in stay out, so a rename does not reindex. ``""`` or ``none``,
    or a name that no router entry has, adds nothing.
    """
    name = getattr(settings, "document_router", "") or ""
    router = (getattr(settings, "document_routers", None) or {}).get(name)
    if name in ("", "none") or router is None:
        return {}
    model = (getattr(settings, "decision_models", None) or {}).get(_entry_value(router, "model"))
    rule = reading_parts.by_name(reading_parts.PAGE_RULES, "document_router")
    return {
        "document_router": {
            "question": _entry_value(router, "question"),
            "threshold": _entry_value(router, "threshold"),
            "images": bool(_entry_value(router, "images", False)),
            "max_chars": _entry_value(router, "max_chars", 2000),
            "model": _decision_model_identity(model),
            "version": rule.version,
        }
    }
