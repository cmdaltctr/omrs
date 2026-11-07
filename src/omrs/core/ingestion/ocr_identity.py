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
- the identity carries what changes the emitted text, and not where files
  live or how they are fetched. A model directory is a filesystem location,
  so the same model under a different path would reindex for nothing.
  Offline mode decides whether a download may happen; its only route to
  different text is whether the model resolves, which the resolved model
  identity records directly (change page-level-ocr-routing, task 4.2);
- the switch, the routing unit and the blank-test version are present for
  every source: ``page`` is the only unit (change page-routing-default).
  The local OCR cuts and models shape PDF text only, so they live in the PDF
  ``parser`` block (:func:`local_backends_payload`, change
  local-ocr-per-backend-cuts, schema 8). A model joins its entry only with a
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


def ocr_routing_payload(settings: Any) -> dict[str, Any]:
    """Return the canonical OCR routing payload from settings.

    Args:
        settings: Settings object (flat ``Settings`` or frozen
            ``EffectiveSettings``) carrying ``ocr_fallback_enabled`` and
            ``ocr_routing_unit``.

    Returns:
        A JSON-ready dict: the routing switch, the routing unit and the
        blank-test version. Every source carries it, so it holds nothing that
        only PDF text depends on: the local OCR cuts and models enter the PDF
        ``parser`` block through :func:`local_backends_payload` (design D8).
        The operational worker settings (folder, timeout) are deliberately
        absent: they shape dispatch, never chunk text.
    """
    # The blank-test version (skip-blank-pages-before-worker): the threshold
    # decides which flagged pages emit no document at all, so a version bump
    # must reindex. Imported at call time so a test can move the version and
    # see the digest follow, the same seam as the maths detector version.
    from ...integrations.pdf.blank_pages import BLANK_PAGE_TEST_VERSION

    return {
        "enabled": settings.ocr_fallback_enabled,
        "routing_unit": settings.ocr_routing_unit,
        "blank_page_test": BLANK_PAGE_TEST_VERSION,
    }


def resolved_routing_payload(settings: Any) -> dict[str, Any]:
    """Build the routing payload for the composition path.

    The local model identity no longer enters this block (schema 8):
    :func:`local_backends_payload` resolves it for the PDF ``parser`` block, so
    this builder probes nothing. Both composition paths still reach the payload
    through this one function.

    Args:
        settings: Settings object carrying the routing switch and the routing
            unit.

    Returns:
        The canonical routing payload.
    """
    return ocr_routing_payload(settings)


def local_backends_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of the local OCR backend list (design D8).

    Every list, the default list included, names each listed backend in list
    order with its effective cut (:func:`omrs.core.reading_parts.effective_cut`)
    and its model once resolved. A model is resolved only when OCR routing is
    on, once per listed backend. PDF sources only:
    :func:`omrs.core.ingestion.reader_identity.pdf_parser_payload` calls it, so
    other sources keep their digest and a cut or model change re-indexes PDF
    sources only.

    Args:
        settings: Settings carrying ``ocr_local_backends``,
            ``ocr_local_cuts`` and ``ocr_fallback_enabled``.

    Returns:
        ``{"local_ocr_backends": {"backends": [{"name", "min_confidence",
        "model"?}, ...]}}``.
    """
    names = tuple(getattr(settings, "ocr_local_backends", DEFAULT_LOCAL_OCR_BACKENDS))
    # A broken discovered backend reads no page, so it adds nothing (finding 4).
    off = broken(KIND_LOCAL_OCR_BACKEND)
    names = tuple(name for name in names if name not in off)
    # Call-time import: pdf-inspector stays out of every import of this module;
    # core reaching into integrations lazily follows the codebase_map precedent.
    from ...integrations.pdf import page_routing

    resolve = getattr(settings, "ocr_fallback_enabled", False)
    backends: list[dict[str, Any]] = []
    for name in names:
        entry: dict[str, Any] = {"name": name, "min_confidence": effective_cut(settings, name)}
        model = (
            page_routing.resolve_local_model_identity(settings, backend=name) if resolve else None
        )
        if model is not None:
            entry["model"] = model
        backends.append(entry)
    return {"local_ocr_backends": {"backends": backends}}


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


def skip_blank_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of the skip-blank switch, empty while it is on.

    Change page-routing-panel, design D4. Off, no page is dropped as blank, so
    PDF text can change: the PDF ``parser`` block gains
    ``skip_blank_pages: false``. On (the default) adds nothing, so every digest
    from before the change stays the same. The entry is PDF-only, so turning
    the switch off re-indexes PDF sources and no other source.
    """
    if getattr(settings, "ocr_skip_blank_pages", True):
        return {}
    return {"skip_blank_pages": False}


def _entry_value(entry: Any, key: str, default: Any = None) -> Any:
    """Return *key* of a settings map entry given as a mapping or as an object."""
    if isinstance(entry, Mapping):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _decision_model_identity(entry: Any, models: Any) -> dict[str, Any]:
    """Return the kind and model identity of a decision model entry (design D9).

    A managed entry adds the SHA-256 of its model and projector files, from the
    ``llamacpp_models`` entry it names (one-llamacpp-router, D3). The address,
    the key and the file paths say where the model lives, not what it is, so
    they stay out.
    """
    if entry is None:
        return {}
    model = _entry_value(entry, "model")
    identity = {"kind": _entry_value(entry, "kind"), "model": model}
    if _entry_value(entry, "server") == "managed":
        listed = next(
            (m for m in (models or {}).values() if _entry_value(m, "model") == model), None
        )
        identity["model_sha256"] = _entry_value(listed, "sha256", None)
        identity["projector_sha256"] = _entry_value(listed, "projector_sha256", None)
    return identity


def document_router_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of the selected router, empty with no router.

    Change document-reading-routers, design D9. The entry holds what decides
    the text: the question, threshold, image flag, character limit, the
    decision model identity and the rule version. The router name, address,
    key and opt-in stay out, so a rename does not reindex. ``""`` or ``none``,
    or a name that no router entry has, adds nothing. ``runnable`` records
    whether the router can judge pages now (:func:`_router_runnable`), so a
    source read while it could not stays stale until it can.
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
            "model": _decision_model_identity(model, getattr(settings, "llamacpp_models", None)),
            "version": rule.version,
            "runnable": _router_runnable(settings),
        }
    }


def _router_runnable(settings: Any) -> bool:
    """Report whether the selected router can judge pages on this host now.

    The router's counterpart of the worker fingerprint's ``available``. True
    only when the PDF path wraps the reader in the OCR seam (the only place
    page rules run), the OCR routes' judge hook gives a page judge whose
    status is ``None``, and an image router has a page renderer. The hook
    keeps ``core`` free of the composition root; with no hook installed
    there is no judge, so the router cannot run. ``router_identity`` builds
    the ``runnable: false`` digest a read whose router failed is stored under.
    """
    from ...integrations.ocr_worker.routes import page_judge
    from ...integrations.pdf import page_images
    from ...integrations.pdf.factory import wraps_ocr_routing
    from .router_identity import router_assumed_not_runnable

    if router_assumed_not_runnable():  # the digest a failed read is stored under
        return False
    if not wraps_ocr_routing(getattr(settings, "pdf_reader", ""), settings):
        return False
    judge = page_judge(settings)
    if judge is None or judge.status is not None:
        return False
    return page_images.available() if judge.images else True
