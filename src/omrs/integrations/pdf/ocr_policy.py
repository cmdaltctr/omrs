"""Shared, immutable PDF routing policy; no core or worker imports."""

from __future__ import annotations

from typing import Any

#: ``pdf_type`` values that require OCR unconditionally (design D7.3
#: routing semantics). Anything else (notably ``text_based`` and
#: ``mixed``) routes by the calibrated thresholds only.
#:
#: ``mixed`` is deliberately NOT here. ``scanned`` and ``image_based``
#: both mean "the whole document is pictures", so no threshold can
#: change the answer. ``mixed`` means "some pages carry text and some do
#: not" — which is precisely the question ``ocr_fallback_page_fraction``
#: exists to answer, so routing it unconditionally skips the one check
#: designed for it. Because task 2.4 dispatches whole files with no
#: page-level stitching, that skip is multiplied by the page count.
#: See ADR-064.
#:
#: Routing and source identity share this pure-data definition.
OCR_UNCONDITIONAL_TYPES: frozenset[str] = frozenset({"scanned", "image_based"})


def ocr_required_by_gate(
    *,
    pdf_type: str,
    pdf_confidence: float,
    pages_needing_ocr: int,
    page_count: int,
    settings: Any,
) -> bool:
    """Decide whether inspection evidence routes a PDF to the OCR worker.

    Reads every threshold from the injected settings object (spec
    pdf-reader: "Routing threshold is read from injected settings" —
    this module contains no threshold constant). A ``0.0`` threshold is
    the packaged "never additionally triggered" sentinel, so at the
    defaults the decision is classification-only.

    Moved from ``ocr_routing.py`` (change skip-blank-pages-before-worker,
    design decision 2) so that module stays under its 500-line ceiling;
    ``ocr_routing`` re-exports it and the seam keeps calling it by name.

    Args:
        pdf_type: ``pdf-inspector`` classification of the PDF.
        pdf_confidence: ``pdf-inspector`` classification confidence.
        pages_needing_ocr: Count of pages the classifier flagged as
            needing OCR (the scalar evidence, not the page list).
        page_count: Total page count of the PDF.
        settings: Injected settings carrying ``ocr_fallback_min_confidence``
            and ``ocr_fallback_page_fraction``.

    Returns:
        True when the PDF is OCR-required under the injected gate.
    """
    if pdf_type in OCR_UNCONDITIONAL_TYPES:
        return True
    min_confidence = settings.ocr_fallback_min_confidence
    # 0.0 is the disabled sentinel: a confidence can never be negative,
    # so a bare `confidence < 0.0` comparison would never fire anyway,
    # but the explicit guard keeps the sentinel semantics readable and
    # protects a future negative-confidence classifier from routing
    # every document at the packaged default.
    if min_confidence > 0.0 and pdf_confidence < min_confidence:
        return True
    fraction = settings.ocr_fallback_page_fraction
    # 0.0 is the disabled sentinel: `0/1 >= 0.0` is always true, so a
    # bare comparison would route every text-based PDF at the packaged
    # default — the opposite of classification-only routing.
    if fraction > 0.0 and page_count > 0 and (pages_needing_ocr / page_count) >= fraction:
        return True
    return False
