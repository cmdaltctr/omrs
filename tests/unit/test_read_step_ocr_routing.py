"""The Read document step reads with its own OCR options (task 4.3, design D4).

Change integrations-show-runtime-components. ``with_read_options`` applies
every set read option to a copy of the node settings. The read adapter asks
the ``ocr`` resource for the routes of those settings, so a node that turns
OCR off reads without OCR, and a node that names another engine sends its
request to that engine. A node that inherits uses the host engine.

The pdf-inspector reader, the page scan, the local OCR tier and the OCR
clients are in-process fakes. The local tier is missing, so the one flagged
page goes to the OCR route of the step settings (page-routing-default).
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Document

from omrs.core.ingestion import graph_adapters
from omrs.core.ingestion.graph_adapters import SourceWork
from omrs.core.ingestion.graph_adapters_catalogue import ReadParams
from omrs.core.ingestion.sources import SourceUnit
from omrs.core.pipelines import CancellationFlag, NodeContext
from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.ocr_worker.routes import OcrRoutes
from omrs.integrations.pdf import factory, maths_routing, ocr_routing

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")


class _Client:
    """An in-process OCR route client that records each request."""

    def __init__(self, backend_id: str) -> None:
        self.fingerprint = SimpleNamespace(
            available=True, protocol_version="1.1", backend_id=backend_id
        )
        self.calls = 0

    def parse(self, pdf_path: str, *, pages: Any = None, timeout: Any = None) -> Any:
        self.calls += 1
        text = f"OCR by {self.fingerprint.backend_id}"
        return make_success("r", text, ocr_backend="x", page_count=1, pages_markdown=[text])


class _Pool:
    """The ``ocr`` resource: routes for the effective settings of a node."""

    def __init__(self) -> None:
        self.clients = {name: _Client(name) for name in ("dots-mocr", "paddleocr-vl")}
        self.threads: list[int] = []

    def routes(self, settings: Any) -> OcrRoutes:
        # The real pool may probe a worker with a blocking subprocess call.
        self.threads.append(threading.get_ident())
        return OcrRoutes((self.clients[settings.ocr_engine_primary],))


class _ScannedPdf:
    """pdf-inspector double: every PDF is a one-page scan that needs OCR."""

    def load_data(self, file: Any, *args: Any, **kwargs: Any) -> list[Document]:
        metadata = {
            "pdf_reader": "pdf_inspector",
            "pdf_type": "scanned",
            "pdf_confidence": 0.95,
            "page_count": 1,
            "pages_needing_ocr": 1,
        }
        return [Document(text="partial native text", metadata=metadata)]


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> _Pool:
    """Read every PDF as one flagged page; return the fake OCR pool."""

    def _no_local_tier(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("no local OCR runtime")

    async def _no_specialised(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(factory, "get_pdf_reader", lambda name, tiers=None: _ScannedPdf())
    monkeypatch.setattr(maths_routing, "maths_font_pages", lambda file: frozenset())
    monkeypatch.setattr(
        ocr_routing,
        "page_evidence",
        lambda file: [SimpleNamespace(page=1, markdown="partial native text", needs_ocr=True)],
    )
    monkeypatch.setattr(ocr_routing, "find_blank_pages", lambda file, pages: frozenset())
    monkeypatch.setattr(ocr_routing, "local_ocr", _no_local_tier)
    monkeypatch.setattr(graph_adapters, "chunk_specialised_source", _no_specialised)
    return _Pool()


async def _read(tmp_path: Path, effective_settings: Any, pool: _Pool, **step: Any) -> Document:
    """Run ``read_adapter`` on a flagged PDF and return the read document."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    host = effective_settings(
        pdf_reader="pdf_inspector", ocr_fallback_enabled=True, ocr_engine_primary="dots-mocr"
    )
    context = NodeContext(
        run_id="r",
        node_id="read",
        settings=host,
        resources={"ocr": pool},
        cancellation=CancellationFlag(),
        collection="documents",
        unit_id="u",
    )
    work = SourceWork(SourceUnit(0, pdf, "scan.pdf", "application/pdf"), "documents")
    out = await graph_adapters.read_adapter(context, {"sources": work}, ReadParams(**step))
    assert host.ocr_fallback_enabled is True and host.ocr_engine_primary == "dots-mocr"
    documents = out.values["documents"].backend_read.documents
    assert len(documents) == 1
    return documents[0]


@pytest.mark.asyncio
async def test_step_that_turns_ocr_off_reads_without_ocr(
    tmp_path: Path, effective_settings: Any, pool: _Pool
) -> None:
    """``ocr_fallback_enabled=False`` on the node: no OCR routing, no OCR request."""
    doc = await _read(tmp_path, effective_settings, pool, ocr_fallback_enabled=False)
    assert doc.text == "partial native text"
    assert "ocr_required" not in doc.metadata, "the OCR routing seam must not wrap the reader"
    assert [c.calls for c in pool.clients.values()] == [0, 0]


@pytest.mark.asyncio
async def test_step_engine_receives_the_request(
    tmp_path: Path, effective_settings: Any, pool: _Pool
) -> None:
    """``ocr_engine_primary=paddleocr-vl`` on the node sends the PDF to that engine."""
    doc = await _read(tmp_path, effective_settings, pool, ocr_engine_primary="paddleocr-vl")
    assert doc.text == "OCR by paddleocr-vl"
    assert pool.clients["paddleocr-vl"].calls == 1
    assert pool.clients["dots-mocr"].calls == 0


@pytest.mark.asyncio
async def test_route_lookup_runs_off_the_event_loop(
    tmp_path: Path, effective_settings: Any, pool: _Pool
) -> None:
    """A route lookup can start a worker probe, so it must not block the loop."""
    await _read(tmp_path, effective_settings, pool, ocr_engine_primary="paddleocr-vl")
    assert pool.threads
    assert threading.get_ident() not in pool.threads


@pytest.mark.asyncio
async def test_inheriting_step_uses_the_host_engine(
    tmp_path: Path, effective_settings: Any, pool: _Pool
) -> None:
    """A node that leaves the engine empty still uses ``dots-mocr``."""
    doc = await _read(tmp_path, effective_settings, pool)
    assert doc.text == "OCR by dots-mocr"
    assert pool.clients["dots-mocr"].calls == 1
    assert pool.clients["paddleocr-vl"].calls == 0


def test_with_read_options_applies_only_set_options(effective_settings: Any) -> None:
    """Set options reach a copy; ``None`` inherits; the host settings stay as they were."""
    from omrs.core.ingestion.graph_adapters_values import with_read_options

    host = effective_settings(pdf_reader="pypdf", ocr_engine_fallback="dots-mocr")
    params = ReadParams(pdf_reader="pdf_inspector", ocr_engine_primary="paddleocr-vl")
    step = with_read_options(host, params)
    assert (step.pdf_reader, step.ocr_engine_primary) == ("pdf_inspector", "paddleocr-vl")
    assert step.ocr_engine_fallback == "dots-mocr"
    assert (host.pdf_reader, host.ocr_engine_primary) == ("pypdf", "dots-mocr")
    assert with_read_options(host, ReadParams()) is host
