"""Literal pins of the hand-typed reading key lists, taken before they are derived.

Change local-ocr-backends, design D15: later groups derive these lists from part
descriptors. Each pin holds today's values and order as a literal, so a derived
list must equal today's list exactly. Every comparison uses a tuple or a list,
never a set, because the order is part of the contract.
"""

from __future__ import annotations

import dataclasses

import pytest

from omrs.config import rules
from omrs.core.ingestion import embed_exclusions, graph_adapters_catalogue
from omrs.core.pipelines import levers


def test_pdf_reader_names_keep_value_and_order() -> None:
    """Pin ``PDF_READER_NAMES`` (D15: a derived reader list keeps this order)."""
    assert rules.PDF_READER_NAMES == (
        "auto",
        "liteparse",
        "pdf_inspector",
        "pypdfium2",
        "pypdf",
    )


def test_document_reading_keys_keep_value_and_order() -> None:
    """Pin ``DOCUMENT_READING_KEYS`` (D15: the HTTP contract order stays)."""
    assert rules.DOCUMENT_READING_KEYS == (
        "pdf_readers",
        "ocr_fallback_enabled",
        "ocr_routing_unit",
        "ocr_engines",
        "ocr_maths_routing_enabled",
        "ocr_non_latin_routing",
        "document_router",
        "ocr_local_backends",
        "ocr_local_cuts",
    )


def test_read_ocr_keys_keep_value_and_order() -> None:
    """Pin ``READ_OCR_KEYS`` (D15: a derived ReadParams key list keeps this order)."""
    assert graph_adapters_catalogue.READ_OCR_KEYS == (
        "ocr_fallback_enabled",
        "ocr_routing_unit",
        "ocr_engines",
        "ocr_engine_primary",
        "ocr_engine_fallback",
        "ocr_maths_routing_enabled",
        "ocr_non_latin_routing",
        "document_router",
        "ocr_local_backends",
    )


def test_read_step_ocr_keys_keep_value_and_order() -> None:
    """Pin ``_READ_STEP_OCR_KEYS`` (D15: a derived lever key list keeps this order)."""
    assert levers._READ_STEP_OCR_KEYS == (
        "ocr_fallback_enabled",
        "ocr_routing_unit",
        "ocr_engines",
        "ocr_engine_primary",
        "ocr_engine_fallback",
        "ocr_maths_routing_enabled",
        "ocr_non_latin_routing",
        "document_router",
        "ocr_local_backends",
    )


def test_excluded_embed_metadata_keys_keep_value_and_order() -> None:
    """Pin the whole excluded-key list (D15: a derived list keeps the order).

    The page-rule keys ``pages_maths_font`` and ``pages_non_latin`` sit inside it
    after the ``ocr_pages_*`` counts, so the slice is pinned with the whole list.
    """
    assert embed_exclusions.EXCLUDED_EMBED_METADATA_KEYS == (
        "pdf_reader",
        "pdf_type",
        "pdf_confidence",
        "ocr_required",
        "ocr_used",
        "ocr_backend",
        "pages_needing_ocr",
        "pages_needing_ocr_before_fallback",
        "extraction_fallback_backend",
        "ocr_pages_native",
        "ocr_pages_local",
        "ocr_pages_worker",
        "ocr_pages_blank",
        "ocr_pages_unresolved",
        "pages_maths_font",
        "pages_non_latin",
        "router_pages_judged",
        "router_pages_accepted",
        "router_pages_rejected",
        "router_pages_unjudged",
        "router_status",
        "page_count",
        "page",
        "page_label",
        "column",
        "section_bbox",
        "bbox_schema_version",
        "file_path",
        "file_type",
        "file_size",
        "creation_date",
        "last_modified_date",
        "last_accessed_date",
    )


def test_identity_unlisted_keys_keep_value() -> None:
    """Pin ``IDENTITY_UNLISTED_KEYS`` (D15: the digest of a default install holds).

    The code value is a frozenset, so the pin is a sorted tuple.
    """
    assert tuple(sorted(embed_exclusions.IDENTITY_UNLISTED_KEYS)) == (
        "pages_non_latin",
        "router_pages_accepted",
        "router_pages_judged",
        "router_pages_rejected",
        "router_pages_unjudged",
        "router_status",
    )


def test_catalogue_pdf_reader_rows_keep_every_field_and_order() -> None:
    """Pin each PDF reader row of the extras catalogue (D15: rows derive in order)."""
    pytest.importorskip("fastapi")
    from omrs.transports.api import integrations_catalogue

    assert [field.name for field in dataclasses.fields(integrations_catalogue.Integration)] == [
        "id",
        "name",
        "purpose",
        "extra",
        "probe",
        "caution",
    ]
    rows = [
        (item.id, item.name, item.purpose, item.extra, item.caution)
        for item in integrations_catalogue.CATALOGUE
        if item.id.startswith("pdf-")
    ]
    assert rows == [
        (
            "pdf-pypdfium2",
            "PDF reader: pypdfium2",
            "Reads PDF pages with the pypdfium2 library.",
            "pdf-pypdfium2",
            None,
        ),
        (
            "pdf-inspector",
            "PDF reader: pdf-inspector",
            "Reads PDF files as Markdown with the pdf-inspector library.",
            "pdf-inspector",
            None,
        ),
    ]
    # The rows sit third and fourth in the whole catalogue, after hybrid. The
    # local OCR backend rows follow them, then leiden.
    ids = [item.id for item in integrations_catalogue.CATALOGUE]
    assert ids[1:6] == [
        "hybrid",
        "pdf-pypdfium2",
        "pdf-inspector",
        "local-ocr-indra",
        "community-leiden",
    ]
