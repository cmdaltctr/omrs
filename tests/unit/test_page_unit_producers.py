"""Every page the page unit emits names the backend that produced its text.

Change local-ocr-backends, task 4.7 and the ``local-ocr-backends`` spec ("A kept
page SHALL name the backend that kept it"). The merge in ``page_routing`` reads
``PageResult.producer``; these tests record the results it receives.

- A worker page always carries the answering engine's ``backend_id``, so the
  ``worker`` fallback in ``_SOURCE_BACKENDS`` is never read (it was deleted).
- A page a local backend keeps carries that backend's producer, and two local
  backends in one document give ``ocr_backend == "mixed"``.
- An unresolved page names the backend whose text it kept.

``pdf_inspector`` is stubbed in ``sys.modules``; the second local backend is a
fake registered with snapshot and restore.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Document

from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.pdf import ocr_routing
from omrs.integrations.pdf.local_ocr import chain, registry
from omrs.integrations.pdf.local_ocr.base import BackendPage
from omrs.integrations.pdf.ocr_routing import OcrRoutedPdfInspector
from omrs.integrations.pdf.page_routing import PAGE_SOURCE_WORKER

ARABIC = "ب" * 300
LATIN = "a" * 300
FAKE = "fake-indra"


class _Inner:
    def load_data(self, file, *args, **kwargs) -> list:
        return [Document(text="native", metadata={"pdf_reader": "pdf_inspector"})]


class _Worker:
    def __init__(self, *, backend_id: str | None = "paddleocr_vl") -> None:
        fingerprint = {"available": True, "protocol_version": "1.1"}
        if backend_id is not None:
            fingerprint["backend_id"] = backend_id
        self.fingerprint = SimpleNamespace(**fingerprint)
        self.calls: list[list[int]] = []

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append(list(pages or []))
        markdown = [f"WORKER {page}" for page in pages or []]
        return make_success(
            "req",
            "\n\n".join(markdown),
            ocr_backend="x",
            page_count=len(markdown),
            pages_markdown=markdown,
        )


class _PdfInspector:
    """``extract_pages_markdown`` flags every page; OCR replays one result per call."""

    def __init__(self, page_count: int, *ocr_calls: dict[int, tuple[str, float]]) -> None:
        self._page_count = page_count
        self._ocr_calls = list(ocr_calls)

    def extract_pages_markdown(self, path):
        pages = [
            SimpleNamespace(page=i, markdown=f"junk {i + 1}", needs_ocr=True, ocr_reason=None)
            for i in range(self._page_count)
        ]
        return SimpleNamespace(pages=pages)

    def process_pdf_with_ocr(self, path, **kwargs):
        result = self._ocr_calls.pop(0)
        pages = []
        for number, (text, confidence) in result.items():
            provenance = SimpleNamespace(
                ocr_confidence=confidence,
                ocr_model=SimpleNamespace(name="pp-ocrv6-small", revision="r"),
                hosted_recommended=False,
            )
            pages.append(SimpleNamespace(page_number=number, markdown=text, provenance=provenance))
        return SimpleNamespace(pages=pages)


class _FakeIndra:
    def __init__(self, result: dict[int, tuple[str, float]]) -> None:
        self._result = result

    def read_pages(self, file, pages, *, settings):
        return [BackendPage(n, *self._result[n], "indra@1") for n in pages if n in self._result]

    def identity(self, settings):
        return "indra@1"


class _Settings:
    """The real settings with the local backend list set (worker B adds the field)."""

    def __init__(self, base: Any, **overrides: Any) -> None:
        self._base = base
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._base, name)


@pytest.fixture(autouse=True)
def isolated_registry():
    state = registry.BACKENDS.snapshot()
    chain.reset_skip_warnings()
    yield
    registry.BACKENDS.restore(state)
    chain.reset_skip_warnings()


@pytest.fixture
def merged(monkeypatch) -> list:
    """Record the page results each merge receives."""
    seen: list = []
    real = ocr_routing.merge_pages

    def _spy(pages, *, page_count):
        seen.append(list(pages))
        return real(pages, page_count=page_count)

    monkeypatch.setattr(ocr_routing, "merge_pages", _spy)
    return seen


def _with_fake_indra(result: dict[int, tuple[str, float]]) -> None:
    registry.register(
        FAKE,
        f"fake.{FAKE}:BACKEND",
        producer="indra_ocr",
        min_confidence=0.94,
        calibrated_by="46a-local-ocr-per-backend-cuts-2026-11-06",
    )
    registry.BACKENDS.cache[FAKE] = _FakeIndra(result)


def _read(monkeypatch, tmp_path, settings, worker, engine: _PdfInspector) -> list:
    monkeypatch.setitem(sys.modules, "pdf_inspector", engine)
    reader = OcrRoutedPdfInspector(_Inner(), settings=settings, ocr_client=worker)
    return reader.load_data(tmp_path / "doc.pdf")


# ── Worker pages (task 4.7) ────────────────────────────────────────────────


@pytest.mark.parametrize("backend_id", ["paddleocr_vl", None])
def test_every_worker_page_carries_a_producer(
    monkeypatch, tmp_path, effective_settings, merged, backend_id
) -> None:
    """Escalated pages read by the worker name the engine, with or without a backend_id."""
    engine = _PdfInspector(3, {1: ("local", 0.95), 2: ("", 0.95), 3: ("low", 0.2)})
    settings = effective_settings(ocr_fallback_enabled=True)

    docs = _read(monkeypatch, tmp_path, settings, _Worker(backend_id=backend_id), engine)

    worker_pages = [page for page in merged[0] if page.source == PAGE_SOURCE_WORKER]
    assert [page.page for page in worker_pages] == [2, 3]
    assert all(page.producer for page in worker_pages), worker_pages
    assert docs[0].metadata["ocr_backend"] == "mixed"


def test_direct_pages_read_by_the_worker_carry_a_producer(
    monkeypatch, tmp_path, effective_settings, merged
) -> None:
    """``always`` sends every flagged page past the local tier, straight to the worker."""
    engine = _PdfInspector(2)
    settings = effective_settings(ocr_fallback_enabled=True, ocr_non_latin_routing="always")

    docs = _read(monkeypatch, tmp_path, settings, _Worker(), engine)

    assert {page.source for page in merged[0]} == {PAGE_SOURCE_WORKER}
    assert all(page.producer == "paddleocr_vl" for page in merged[0])
    assert docs[0].metadata["ocr_backend"] == "paddleocr_vl"


# ── Local backend producers and ``mixed`` (task 4.7, design D14) ───────────


def test_two_local_backends_in_one_document_give_mixed(
    monkeypatch, tmp_path, effective_settings, merged
) -> None:
    """Indra keeps page 1 (Arabic) at its cut; page 2 (Latin) is below it and PP-OCRv6 keeps it."""
    _with_fake_indra({1: (ARABIC, 0.95), 2: (LATIN, 0.80)})
    engine = _PdfInspector(2, {2: ("latin text", 0.95)})
    base = effective_settings(ocr_fallback_enabled=True)
    settings = _Settings(base, ocr_local_backends=(FAKE, "pp-ocrv6-small"))

    docs = _read(monkeypatch, tmp_path, settings, _Worker(), engine)

    producers = {page.page: (page.source, page.producer) for page in merged[0]}
    assert producers == {1: ("local", "indra_ocr"), 2: ("local", "pdf_inspector_ocr")}
    assert docs[0].metadata["ocr_backend"] == "mixed"
    assert docs[0].metadata["ocr_pages_local"] == 2


def test_the_default_backend_names_the_producer_before_the_change(
    monkeypatch, tmp_path, effective_settings, merged
) -> None:
    engine = _PdfInspector(1, {1: ("local", 0.95)})

    docs = _read(monkeypatch, tmp_path, effective_settings(ocr_fallback_enabled=True), None, engine)

    assert merged[0][0].producer == "pdf_inspector_ocr"
    assert docs[0].metadata["ocr_backend"] == "pdf_inspector_ocr"


def test_an_unresolved_page_names_the_backend_whose_text_it_kept(
    monkeypatch, tmp_path, effective_settings, merged
) -> None:
    """No engine: the page keeps Indra's text, the first listed text, and names Indra."""
    _with_fake_indra({1: (ARABIC, 0.80)})
    engine = _PdfInspector(1, {1: ("pp text", 0.5)})
    base = effective_settings(ocr_fallback_enabled=True)
    settings = _Settings(base, ocr_local_backends=(FAKE, "pp-ocrv6-small"))

    docs = _read(monkeypatch, tmp_path, settings, None, engine)

    page = merged[0][0]
    assert (page.source, page.producer, page.text) == ("unresolved", "indra_ocr", ARABIC)
    assert docs[0].metadata["ocr_backend"] == "indra_ocr"
    assert docs[0].metadata["ocr_pages_unresolved"] == 1
