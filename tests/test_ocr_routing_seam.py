"""Routing-seam tests through the reader contract (tasks 2.3–2.5, 2.7, 2.8, 2.10).

Reader-level coverage against the committed calibration fixtures and
the stub worker, under the ``page`` routing unit (the only unit since
change page-routing-default): clean text-based PDFs never start the
worker, complex text layouts stay on pdf-inspector, a scanned fixture
sends its flagged page to the worker and reuses one process, an
unavailable worker degrades deterministically, and every branch stamps
the four additive OCR diagnostics with ``pages_needing_ocr`` as a scalar
count.

The local OCR tier and the blank test are stubbed (a missing runtime and
no blank page), so the result never depends on the PDFium or ONNX Runtime
libraries of the machine.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from omrs.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrs.integrations.ocr_worker.managed import ManagedOcrClient
from omrs.integrations.pdf.factory import build_pdf_reader
from omrs.integrations.pdf.ocr_routing import (
    OCR_BACKEND_FAST_PATH,
    OcrRoutedPdfInspector,
)
from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

pdf_inspector_lib = pytest.importorskip(
    "pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
#: The stub worker's fingerprint reports this backend_id; the worker path
#: stamps the answering engine's backend_id (modular-ocr-workers-dots-mocr).
OCR_BACKEND_WORKER_PATH = "paddleocr_vl"
CALIBRATION = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command (protocol 1.1: page-listed requests)."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode, "--protocol-version", "1.1"]


@pytest.fixture(autouse=True)
def _no_local_runtime(monkeypatch) -> None:
    """Make the local OCR tier a missing runtime and the blank test find nothing."""
    from omrs.integrations.pdf import ocr_routing

    def _missing(*args, **kwargs):
        raise ValueError("failed to load ONNX Runtime (stubbed)")

    monkeypatch.setattr(ocr_routing, "local_ocr", _missing)
    monkeypatch.setattr(ocr_routing, "find_blank_pages", lambda file, pages: frozenset())


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Isolate probe memoisation between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


def _echo_client() -> ManagedOcrClient:
    """A managed client around the healthy echo stub worker."""
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available
    return ManagedOcrClient(fingerprint=fingerprint, command=_stub_command("echo"))


def _routed_reader(client: ManagedOcrClient | None, effective_settings) -> OcrRoutedPdfInspector:
    """Build the seam exactly as the factory composes it (fallback on)."""
    reader = build_pdf_reader(
        "pdf_inspector",
        effective_settings(pdf_reader="pdf_inspector", ocr_fallback_enabled=True),
        ocr_client=client,
    )
    assert isinstance(reader, OcrRoutedPdfInspector)
    return reader


# ── Task 2.8: laziness — clean PDFs never start the worker ────────────────


def test_clean_text_pdf_never_starts_the_worker(effective_settings) -> None:
    """A clean text-based PDF neither spawns the process nor loads its model."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_clean_text.pdf")
        meta = docs[0].metadata
        assert meta["ocr_required"] is False
        assert meta["ocr_used"] is False
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
        assert meta["pages_needing_ocr"] == 0
        assert client.is_started is False
        assert client.process_generations == 0
    finally:
        client.close()


def test_complex_text_layout_stays_on_pdf_inspector(effective_settings) -> None:
    """The table-heavy calibration fixture never reaches the worker (task 2.5).

    cal_table_text.pdf is the committed complex-layout calibration
    fixture: text_based at confidence 1.0 with no flagged pages.
    Layout complexity alone must not select OCR.
    """
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_table_text.pdf")
        meta = docs[0].metadata
        assert meta["pdf_type"] == "text_based"
        assert meta["ocr_required"] is False
        assert meta["ocr_used"] is False
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
        assert client.process_generations == 0
    finally:
        client.close()


def test_fallback_disabled_returns_the_plain_reader(effective_settings) -> None:
    """With OCR_FALLBACK_ENABLED=false the factory composes no seam at all."""
    reader = build_pdf_reader(
        "pdf_inspector",
        effective_settings(pdf_reader="pdf_inspector", ocr_fallback_enabled=False),
    )
    assert type(reader) is PdfInspectorReader


def test_packaged_default_composes_the_seam(effective_settings) -> None:
    """The promoted default wraps pdf_inspector in the routing seam (ADR-065)."""
    reader = build_pdf_reader("pdf_inspector", effective_settings(pdf_reader="pdf_inspector"))
    assert isinstance(reader, OcrRoutedPdfInspector)


# ── Tasks 2.3/2.4: a scanned fixture sends its flagged page ───────────────


def test_scanned_fixture_sends_its_flagged_page_to_the_worker(effective_settings) -> None:
    """The worker's page text replaces the empty native page."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert len(docs) == 1
        meta = docs[0].metadata
        assert docs[0].get_content() == "# Stub page 1"
        assert meta["ocr_required"] is True
        assert meta["ocr_used"] is True
        assert meta["ocr_backend"] == OCR_BACKEND_WORKER_PATH
        assert meta["ocr_pages_worker"] == 1
        assert meta["page"] == 1
        # Honest provenance: the inspection evidence stays authoritative.
        assert meta["pdf_type"] == "scanned"
        assert meta["page_count"] == 1
        assert client.is_started is True
        assert client.process_generations == 1
    finally:
        client.close()


def test_second_ocr_request_reuses_the_same_process(effective_settings) -> None:
    """Two scanned files, one subprocess (single spawn assertion)."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        underlying = client._client
        assert underlying is not None and underlying._process is not None
        first_pid = underlying._process.pid
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert docs[0].metadata["ocr_used"] is True
        assert client.process_generations == 1
        reused = client._client
        assert reused is not None and reused._process is not None
        assert reused._process.pid == first_pid
    finally:
        client.close()


# ── Task 2.7: unavailable worker degrades deterministically ───────────────


def test_unavailable_client_keeps_partial_markdown_and_degrades(effective_settings, caplog) -> None:
    """ocr_required=True, ocr_used=False: honest degradation, no fabrication."""
    reader = _routed_reader(None, effective_settings)  # no client wired
    with caplog.at_level("WARNING"):
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
    meta = docs[0].metadata
    assert meta["ocr_required"] is True
    assert meta["ocr_used"] is False
    assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
    assert meta["pages_needing_ocr"] == 1
    assert meta["ocr_pages_unresolved"] == 1
    # The partial (empty) pdf-inspector markdown is kept as-is.
    assert docs[0].get_content() == ""
    assert "OCR_WORKERS_DIR" in caplog.text
    assert "Local OCR tier unavailable" in caplog.text


def test_unavailable_fingerprint_client_degrades_the_same_way(effective_settings) -> None:
    """A probed-unavailable fingerprint degrades identically to no client."""
    from omrs.capabilities import UNAVAILABLE_OCR_WORKER_FINGERPRINT

    client = ManagedOcrClient(
        fingerprint=UNAVAILABLE_OCR_WORKER_FINGERPRINT, command=_stub_command("echo")
    )
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert docs[0].metadata["ocr_required"] is True
        assert docs[0].metadata["ocr_used"] is False
        assert client.process_generations == 0  # never spawned
    finally:
        client.close()


def test_degraded_result_still_indexes_as_a_document(effective_settings) -> None:
    """The degraded path returns a usable Document, never an exception."""
    reader = _routed_reader(None, effective_settings)
    docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
    assert len(docs) == 1
    assert docs[0].metadata["file_name"] == "cal_scanned.pdf"


# ── Task 2.10: diagnostics shape on every branch ──────────────────────────


@pytest.mark.parametrize("fixture", ["cal_clean_text.pdf", "cal_table_text.pdf", "cal_scanned.pdf"])
def test_pages_needing_ocr_is_a_scalar_on_every_branch(fixture: str, effective_settings) -> None:
    """Stored metadata carries a scalar int count, never the page list."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / fixture)
        value = docs[0].metadata["pages_needing_ocr"]
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value in (0, 1)
    finally:
        client.close()


# ── Every document carries the page-source counts ─────────────────────────


def test_a_clean_text_pdf_carries_the_page_source_counts(effective_settings) -> None:
    """With page routing the only unit, even a clean PDF reports its merge."""
    from omrs.integrations.pdf.page_routing import _COUNT_KEYS

    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        documents = reader.load_data(file=CALIBRATION / "cal_clean_text.pdf")
    finally:
        client.close()

    for document in documents:
        meta = document.metadata
        assert set(_COUNT_KEYS.values()) <= set(meta)
        assert meta["ocr_pages_native"] == meta["page_count"]
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH


def test_page_source_count_keys_are_all_excluded_from_embedding_text() -> None:
    """Every count is parser telemetry, so none may reach embedding text.

    They are constant across a document's chunks and would otherwise be
    embedded into every one of them.
    """
    from omrs.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS
    from omrs.integrations.pdf.page_routing import _COUNT_KEYS

    assert set(_COUNT_KEYS.values()) <= set(EXCLUDED_EMBED_METADATA_KEYS)


def test_page_unit_counts_never_reach_embedding_text() -> None:
    """A page-unit document's embedding text contains none of the four counts.

    The exclusion set is what keeps them out; this checks the text a Document
    would hand the embedding model, not just the membership of a tuple.
    """
    from llama_index.core import Document

    from omrs.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS
    from omrs.integrations.pdf.page_routing import _COUNT_KEYS

    document = Document(
        text="page one",
        metadata={key: 3 for key in _COUNT_KEYS.values()} | {"pdf_reader": "pdf_inspector"},
        excluded_embed_metadata_keys=list(EXCLUDED_EMBED_METADATA_KEYS),
    )

    embedded = document.get_content(metadata_mode="embed")

    for key in _COUNT_KEYS.values():
        assert key not in embedded
    assert "page one" in embedded
