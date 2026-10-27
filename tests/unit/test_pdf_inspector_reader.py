"""Tests for the pdf_inspector reader adapter.

Contract for the new ``pdf-inspector`` backend (PyPI extra
``pdf-inspector``, Python module ``pdf_inspector``): factory resolution,
lazy import of the optional package, markdown extraction passthrough, and
an actionable ImportError when the extra is missing.

The package is NOT installed in the test venv. No test performs real PDF
parsing and nothing touches the network: the import path is either stubbed
in ``sys.modules`` or forced to fail, following the mocking pattern used
for optional backends elsewhere in this suite.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from omrs.integrations.pdf.factory import get_pdf_reader
from omrs.integrations.pdf.registry import available as available_readers


def _stub_pdf_inspector(
    monkeypatch,
    markdown: str,
    *,
    pdf_type: str = "text_based",
    confidence: float = 1.0,
    page_count: int = 1,
    pages_needing_ocr: list[int] | None = None,
    pages: list[str] | None = None,
    pages_error: Exception | None = None,
) -> MagicMock:
    """Install a fake ``pdf_inspector`` module in ``sys.modules``.

    The stub mirrors the real package API: ``process_pdf(path)`` returns
    an object carrying ``markdown``, ``pdf_type``, ``confidence``,
    ``page_count`` and the ``pages_needing_ocr`` page list.
    ``extract_pages_markdown(path)`` returns ``PageMarkdown``-shaped pages
    numbered from 0, as the real library does. Without ``pages``, the
    per-page result holds the whole Markdown as page 0 (or ``page_count``
    empty pages when the Markdown is empty). A MagicMock backs the module
    so any import shape the adapter uses resolves without the package
    installed.
    """
    stub = MagicMock()
    result = stub.process_pdf.return_value
    result.markdown = markdown
    result.pdf_type = pdf_type
    result.confidence = confidence
    result.page_count = page_count
    result.pages_needing_ocr = pages_needing_ocr or []
    if pages is None:
        pages = [markdown] if markdown else [""] * page_count
    if pages_error is not None:
        stub.extract_pages_markdown.side_effect = pages_error
    else:
        scan = stub.extract_pages_markdown.return_value
        scan.pages = [_page_markdown(index, text) for index, text in enumerate(pages)]
        scan.pages_needing_ocr = pages_needing_ocr or []
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    return stub


def _page_markdown(index: int, text: str) -> SimpleNamespace:
    """Return a ``PageMarkdown``-shaped page; ``page`` is 0-based like the library."""
    return SimpleNamespace(page=index, markdown=text, needs_ocr=False, ocr_reason=None)


def _fake_pdf(tmp_path, name: str = "sample.pdf"):
    """Write a stub PDF file (never parsed: the library is stubbed)."""
    fake_pdf = tmp_path / name
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    return fake_pdf


def _stub_liteparse_retry(monkeypatch, page_texts: list[str]) -> None:
    """Seed the registry cache with a stub LiteParse fallback reader."""
    from llama_index.core import Document

    from omrs.integrations.pdf import registry

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            self.ocr_enabled = ocr_enabled
            self.num_workers = num_workers

        def load_data(self, file, *args, **kwargs):
            return [Document(text=text) for text in page_texts]

    monkeypatch.setitem(registry._cache, "liteparse", _StubLiteParseReader)


def _stub_pypdf_retry(monkeypatch, page_texts: list[str]) -> None:
    """Seed the reader registry cache with a stub pypdf fallback reader.

    The guard resolves the retry through ``registry.get("pypdf")``, which
    consults ``_cache`` first, so seeding the cache stubs the fallback
    without touching the real reader or the network.
    """
    from llama_index.core import Document

    from omrs.integrations.pdf import registry

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text=text) for text in page_texts]

    monkeypatch.setitem(registry._cache, "pypdf", _StubPypdfReader)


def _stub_liteparse_exploding(monkeypatch) -> None:
    """Seed a LiteParse tier that fails if a no-retry path invokes it."""
    from omrs.integrations.pdf import registry

    class _ExplodingReader:
        def __init__(self, *, ocr_enabled: bool = False, num_workers: int | None = None) -> None:
            self.ocr_enabled = ocr_enabled
            self.num_workers = num_workers

        def load_data(self, file, *args, **kwargs):
            raise AssertionError("liteparse retry must not run on this path")

    monkeypatch.setitem(registry._cache, "liteparse", _ExplodingReader)


def _stub_pypdf_exploding(monkeypatch) -> None:
    """Seed a fallback reader that fails the test if it is ever invoked."""
    from omrs.integrations.pdf import registry

    class _ExplodingReader:
        def load_data(self, file, *args, **kwargs):
            raise AssertionError("pypdf retry must not run on this path")

    monkeypatch.setitem(registry._cache, "pypdf", _ExplodingReader)


def test_factory_registers_pdf_inspector_name():
    """The registry advertises pdf_inspector as a concrete reader."""
    assert "pdf_inspector" in available_readers()


def test_factory_resolves_pdf_inspector_reader():
    """get_pdf_reader('pdf_inspector') returns an object with load_data."""
    reader = get_pdf_reader("pdf_inspector")
    assert callable(reader.load_data)


def test_adapter_module_imports_pdf_inspector_lazily(monkeypatch):
    """Importing the adapter module must not import the optional package."""
    # delitem (not a bare pop) so teardown restores the module: a permanent
    # eviction leaves the cached ``pdf_inspector.pdf_inspector`` submodule
    # parentless, and the next real import half-initialises with a
    # NameError inside the package ``__init__`` (surfaced when an
    # earlier-running test exercises the real reader).
    monkeypatch.delitem(sys.modules, "pdf_inspector", raising=False)

    importlib.import_module("omrs.integrations.pdf.pdf_inspector")

    assert "pdf_inspector" not in sys.modules


def test_load_data_passthroughs_mock_markdown(monkeypatch, tmp_path):
    """With pdf_inspector stubbed, load_data returns Documents carrying the markdown."""
    markdown = "# Title\n\nBody text extracted by pdf-inspector."
    _stub_pdf_inspector(monkeypatch, markdown)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert isinstance(documents, list)
    assert len(documents) > 0
    for doc in documents:
        assert isinstance(doc.text, str)
        assert markdown in doc.text
        assert doc.metadata.get("pdf_reader") == "pdf_inspector"


def test_missing_package_raises_actionable_importerror(monkeypatch, tmp_path):
    """Without pdf_inspector installed, load_data raises an ImportError naming the fix."""
    monkeypatch.setitem(sys.modules, "pdf_inspector", None)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ImportError) as excinfo:
        PdfInspectorReader().load_data(file=fake_pdf)

    message = str(excinfo.value)
    assert "pdf_inspector" in message
    assert "install" in message.lower()
    assert "uv sync" in message


def test_real_pdf_end_to_end_smoke(fixtures_dir):
    """The packaged default reader parses a real fixture PDF end to end.

    CI forces ``PDF_READER=pypdf`` for the deterministic suite, so the
    promoted default has no real-execution coverage unless a test invokes
    the adapter against an actual PDF. This is that test: the real
    ``pdf_inspector`` package, a real text PDF (hand-built minimal
    fixture — the five ``pdf_dir`` fixtures are synthetic shells that
    classify as scanned with no text layer), real markdown output.
    """
    from pathlib import Path

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    pdf = fixtures_dir / "smoke_text.pdf"
    assert isinstance(pdf, Path)

    docs = PdfInspectorReader().load_data(file=pdf)

    assert len(docs) == 1
    meta = docs[0].metadata
    assert meta["pdf_reader"] == "pdf_inspector"
    assert meta["pdf_type"] == "text_based"
    assert meta["page_count"] == 1
    content = docs[0].get_content()
    assert "Smoke Test Document" in content, content[:200]


# ── Sloman guard: text_based-but-empty contradiction retries by tier ──


def test_contradiction_retries_with_liteparse_before_pypdf_and_recovers_text(monkeypatch, tmp_path):
    """A contradiction keeps the LiteParse tier's pages and names it honestly."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, ["lite page one", "lite page two", "lite page three"])
    _stub_pypdf_retry(monkeypatch, ["pypdf must not be selected"])

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert [doc.get_content() for doc in documents] == [
        "lite page one",
        "lite page two",
        "lite page three",
    ]
    assert all(doc.metadata["extraction_fallback_backend"] == "liteparse" for doc in documents)


def test_unavailable_liteparse_falls_through_to_pypdf(monkeypatch, tmp_path):
    """An unavailable LiteParse tier hands over to the registered pypdf tier."""
    from llama_index.core import Document

    from omrs.integrations.pdf import registry
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=2, pages_needing_ocr=[0, 1])
    calls: list[str] = []

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf page one"), Document(text="pypdf page two")]

    def _get_reader(name: str):
        calls.append(name)
        if name == "liteparse":
            raise ImportError("liteparse is not installed")
        assert name == "pypdf"
        return _StubPypdfReader

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert calls == ["liteparse", "pypdf"]
    assert [doc.get_content() for doc in documents] == ["pypdf page one", "pypdf page two"]
    assert all(doc.metadata["extraction_fallback_backend"] == "pypdf" for doc in documents)


@pytest.mark.parametrize("liteparse_failure", ["raises", "empty"])
def test_failed_liteparse_tier_hands_over_to_pypdf(monkeypatch, tmp_path, liteparse_failure):
    """A LiteParse exception or empty result must not block the pypdf rescue."""
    from llama_index.core import Document

    from omrs.integrations.pdf import registry
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=2, pages_needing_ocr=[0, 1])
    calls: list[str] = []

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None) -> None:
            assert ocr_enabled is False
            assert num_workers is None

        def load_data(self, file, *args, **kwargs):
            if liteparse_failure == "raises":
                raise ValueError("LiteParse could not read this PDF")
            return [Document(text=""), Document(text="")]

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf rescue")]

    def _get_reader(name: str):
        calls.append(name)
        return {"liteparse": _StubLiteParseReader, "pypdf": _StubPypdfReader}[name]

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    document = PdfInspectorReader().load_data(file=fake_pdf)[0]

    assert calls == ["liteparse", "pypdf"]
    assert document.get_content() == "pypdf rescue"
    assert document.metadata["extraction_fallback_backend"] == "pypdf"


def test_recovered_text_corrects_the_routing_evidence(monkeypatch, tmp_path):
    """A successful retry zeroes the flagged count and keeps the original."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, [""] * 3)
    _stub_pypdf_retry(monkeypatch, ["recovered text"] * 3)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    meta = PdfInspectorReader().load_data(file=fake_pdf)[0].metadata

    # Corrected scalar evidence: the pages were flagged only because the
    # pdf-inspector extraction was empty.
    assert meta["pages_needing_ocr"] == 0
    assert meta["pages_needing_ocr_before_fallback"] == 3
    assert meta["extraction_fallback_backend"] == "pypdf"
    # The classification was right; only the extraction failed.
    assert meta["pdf_type"] == "text_based"
    assert meta["pdf_confidence"] == 1.0
    assert meta["page_count"] == 3
    assert meta["pdf_reader"] == "pdf_inspector"


def test_both_tiers_empty_emit_the_unchanged_inspector_result(monkeypatch, tmp_path):
    """When both tiers yield no text, the original flagged result stands."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_retry(monkeypatch, ["", "", ""])
    _stub_pypdf_retry(monkeypatch, ["", "", ""])

    from omrs.integrations.pdf import registry
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    calls: list[str] = []
    registered_get = registry.get

    def _get_reader(name: str):
        calls.append(name)
        return registered_get(name)

    monkeypatch.setattr(registry, "get", _get_reader)

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert calls == ["liteparse", "pypdf"]
    assert len(documents) == 1
    assert documents[0].get_content() == ""
    meta = documents[0].metadata
    assert meta["pages_needing_ocr"] == 3
    assert "pages_needing_ocr_before_fallback" not in meta
    assert "extraction_fallback_backend" not in meta


def test_retry_exception_propagates_to_the_error_boundary(monkeypatch, tmp_path):
    """A last-tier pypdf crash on an opened file reaches the error boundary."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )

    from omrs.integrations.pdf import registry

    class _CrashingReader:
        def load_data(self, file, *args, **kwargs):
            raise ValueError("encrypted or malformed PDF")

    _stub_liteparse_retry(monkeypatch, ["", "", ""])
    monkeypatch.setitem(registry._cache, "pypdf", _CrashingReader)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sloman.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    with pytest.raises(ValueError, match="encrypted or malformed"):
        PdfInspectorReader().load_data(file=fake_pdf)


def test_liteparse_retry_forces_ocr_disabled(monkeypatch, tmp_path, effective_settings):
    """The rescue tier disables LiteParse OCR despite an operator default."""
    from llama_index.core import Document

    from omrs.core.settings import set_default_effective_settings
    from omrs.integrations.pdf import registry
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    set_default_effective_settings(effective_settings(liteparse_ocr_enabled=True))
    _stub_pdf_inspector(monkeypatch, "", page_count=1, pages_needing_ocr=[0])
    observed_settings: list[tuple[bool, int | None]] = []

    class _StubLiteParseReader:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None) -> None:
            observed_settings.append((ocr_enabled, num_workers))

        def load_data(self, file, *args, **kwargs):
            return [Document(text="extraction-only rescue")]

    class _StubPypdfReader:
        def load_data(self, file, *args, **kwargs):
            return [Document(text="pypdf must not be selected")]

    monkeypatch.setitem(registry._cache, "liteparse", _StubLiteParseReader)
    monkeypatch.setitem(registry._cache, "pypdf", _StubPypdfReader)

    document = PdfInspectorReader().load_data(file=tmp_path / "sloman.pdf")[0]

    assert observed_settings == [(False, None)]
    assert document.get_content() == "extraction-only rescue"
    assert document.metadata["extraction_fallback_backend"] == "liteparse"


def test_liteparse_rescue_does_not_require_default_settings(monkeypatch, tmp_path):
    """A bare adapter call stays on liteparse without composed settings."""
    from omrs.core.settings import reset_default_effective_settings
    from omrs.integrations.pdf import registry
    from omrs.integrations.pdf.liteparse import LiteParseReader
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    _stub_pdf_inspector(monkeypatch, "", page_count=1, pages_needing_ocr=[0])
    observed_settings: list[tuple[bool, int | None, bool]] = []

    class _StubLiteParse:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None, quiet: bool) -> None:
            observed_settings.append((ocr_enabled, num_workers, quiet))

        def parse(self, file):
            item = MagicMock(text="standalone liteparse rescue")
            item.x = item.y = 0.0
            item.width = item.height = 10.0
            page = MagicMock(page_num=1, text_items=[item])
            return MagicMock(pages=[page])

    stub_module = MagicMock(LiteParse=_StubLiteParse)
    monkeypatch.setitem(sys.modules, "liteparse", stub_module)
    monkeypatch.setitem(registry._cache, "liteparse", LiteParseReader)
    _stub_pypdf_exploding(monkeypatch)
    reset_default_effective_settings()

    fake_pdf = tmp_path / "standalone.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")
    document = PdfInspectorReader().load_data(file=fake_pdf)[0]

    assert observed_settings == [(False, None, True)]
    assert document.get_content() == "standalone liteparse rescue"
    assert document.metadata["extraction_fallback_backend"] == "liteparse"


# ── No-retry paths: the guard must never fire outside the contradiction ──


def test_non_empty_markdown_never_retries(monkeypatch, tmp_path):
    """A normal text_based extraction carries no fallback diagnostics."""
    markdown = "# Title\n\nBody text extracted by pdf-inspector."
    _stub_pdf_inspector(
        monkeypatch,
        markdown,
        page_count=3,
        pages_needing_ocr=[1],
    )
    _stub_liteparse_exploding(monkeypatch)
    _stub_pypdf_exploding(monkeypatch)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == markdown
    meta = documents[0].metadata
    assert meta["pages_needing_ocr"] == 1
    assert "extraction_fallback_backend" not in meta
    assert "pages_needing_ocr_before_fallback" not in meta


def test_scanned_classification_never_retries(monkeypatch, tmp_path):
    """Non-text_based classifications keep their empty markdown as-is."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        pdf_type="scanned",
        confidence=0.9,
        page_count=3,
        pages_needing_ocr=[0, 1, 2],
    )
    _stub_liteparse_exploding(monkeypatch)
    _stub_pypdf_exploding(monkeypatch)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "scanned.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    assert documents[0].get_content() == ""
    meta = documents[0].metadata
    assert meta["pdf_type"] == "scanned"
    assert meta["pages_needing_ocr"] == 3
    assert "extraction_fallback_backend" not in meta


def test_zero_page_count_never_retries(monkeypatch, tmp_path):
    """An empty file emits no contradiction — nothing was there to read."""
    _stub_pdf_inspector(
        monkeypatch,
        "",
        page_count=0,
        pages_needing_ocr=[],
    )
    _stub_liteparse_exploding(monkeypatch)
    _stub_pypdf_exploding(monkeypatch)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 stub")

    documents = PdfInspectorReader().load_data(file=fake_pdf)

    assert len(documents) == 1
    meta = documents[0].metadata
    assert meta["page_count"] == 0
    assert "extraction_fallback_backend" not in meta


# ── Page documents (change pdf-inspector-page-provenance, design D1-D3) ──

_EVIDENCE_KEYS = (
    "pdf_reader",
    "pdf_type",
    "pdf_confidence",
    "page_count",
    "pages_needing_ocr",
    "file_path",
    "file_name",
)


def _three_page_read(monkeypatch, tmp_path, pages: list[str]) -> tuple[list, MagicMock]:
    """Read a stubbed 3-page text PDF whose per-page result is *pages*."""
    stub = _stub_pdf_inspector(
        monkeypatch,
        "\n\n".join(text for text in pages if text.strip()),
        page_count=3,
        pages_needing_ocr=[2],
        pages=pages,
    )
    _stub_liteparse_exploding(monkeypatch)
    _stub_pypdf_exploding(monkeypatch)

    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    return PdfInspectorReader().load_data(file=_fake_pdf(tmp_path)), stub


class TestPageDocuments:
    """Task 2.1: one document per page with text, numbered from 1."""

    def test_three_pages_give_three_documents_in_order(self, monkeypatch, tmp_path):
        """Spec scenario "Three-page PDF gives three page documents"."""
        documents, _ = _three_page_read(monkeypatch, tmp_path, ["# One", "Two body", "Three body"])

        assert [doc.text for doc in documents] == ["# One", "Two body", "Three body"]

    def test_pages_are_one_based_ints_with_string_labels(self, monkeypatch, tmp_path):
        """Spec scenario "The first page is page 1": library page 0 becomes page 1."""
        documents, _ = _three_page_read(monkeypatch, tmp_path, ["one", "two", "three"])

        assert [doc.metadata["page"] for doc in documents] == [1, 2, 3]
        assert all(type(doc.metadata["page"]) is int for doc in documents)
        assert [doc.metadata["page_label"] for doc in documents] == ["1", "2", "3"]

    @pytest.mark.parametrize("blank", ["", "  \n\t "])
    def test_page_without_text_emits_no_document(self, monkeypatch, tmp_path, blank):
        """Spec scenario "A page without text emits no document"."""
        documents, _ = _three_page_read(monkeypatch, tmp_path, ["one", blank, "three"])

        assert [doc.metadata["page"] for doc in documents] == [1, 3]
        assert [doc.text for doc in documents] == ["one", "three"]

    def test_every_page_carries_the_same_whole_pdf_evidence(self, monkeypatch, tmp_path):
        """Spec requirement "Every pdf_inspector page document carries the whole-PDF evidence"."""
        documents, _ = _three_page_read(monkeypatch, tmp_path, ["one", "two", "three"])

        assert len(documents) == 3
        expected = {key: documents[0].metadata[key] for key in _EVIDENCE_KEYS}
        assert expected["pdf_reader"] == "pdf_inspector"
        assert expected["pdf_type"] == "text_based"
        assert expected["page_count"] == 3
        assert expected["pages_needing_ocr"] == 1
        assert expected["file_name"] == "sample.pdf"
        for doc in documents:
            assert {key: doc.metadata[key] for key in _EVIDENCE_KEYS} == expected

    def test_each_library_call_runs_once(self, monkeypatch, tmp_path):
        """Design D1: ``process_pdf`` and ``extract_pages_markdown`` once each."""
        _, stub = _three_page_read(monkeypatch, tmp_path, ["one", "two", "three"])

        stub.process_pdf.assert_called_once()
        stub.extract_pages_markdown.assert_called_once()


class TestWholeDocumentFallback:
    """Task 2.2: the per-page result cannot be used (design D3)."""

    def test_per_page_failure_emits_whole_markdown_without_page(
        self, monkeypatch, tmp_path, caplog
    ):
        """Spec scenario "Per-page extraction raises"."""
        _stub_pdf_inspector(
            monkeypatch,
            "# Whole\n\nbody",
            page_count=2,
            pages_error=RuntimeError("per-page parse failed"),
        )
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        with caplog.at_level("WARNING", logger="omrs.integrations.pdf.pdf_inspector"):
            documents = PdfInspectorReader().load_data(file=_fake_pdf(tmp_path, "broken.pdf"))

        assert len(documents) == 1
        assert documents[0].text == "# Whole\n\nbody"
        assert "page" not in documents[0].metadata
        assert "page_label" not in documents[0].metadata
        assert documents[0].metadata["page_count"] == 2
        assert any(
            record.levelname == "WARNING" and "broken.pdf" in record.getMessage()
            for record in caplog.records
        )

    def test_per_page_without_text_emits_whole_markdown_without_page(
        self, monkeypatch, tmp_path, caplog
    ):
        """No page text while ``process_pdf`` has text: the same safe floor."""
        _stub_pdf_inspector(monkeypatch, "# Whole", page_count=2, pages=["", " "])
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        with caplog.at_level("WARNING", logger="omrs.integrations.pdf.pdf_inspector"):
            documents = PdfInspectorReader().load_data(file=_fake_pdf(tmp_path, "blank.pdf"))

        assert len(documents) == 1
        assert documents[0].text == "# Whole"
        assert "page" not in documents[0].metadata
        assert "page_label" not in documents[0].metadata
        assert any("blank.pdf" in record.getMessage() for record in caplog.records)

    def test_nothing_has_text_emits_one_empty_document(self, monkeypatch, tmp_path):
        """Spec scenario "No page has text": the classification survives for OCR routing."""
        _stub_pdf_inspector(
            monkeypatch,
            "",
            pdf_type="scanned",
            confidence=0.9,
            page_count=2,
            pages_needing_ocr=[1, 2],
            pages=["", ""],
        )
        _stub_liteparse_exploding(monkeypatch)
        _stub_pypdf_exploding(monkeypatch)
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        documents = PdfInspectorReader().load_data(file=_fake_pdf(tmp_path))

        assert len(documents) == 1
        assert documents[0].text == ""
        meta = documents[0].metadata
        assert "page" not in meta
        assert "page_label" not in meta
        assert meta["pdf_type"] == "scanned"
        assert meta["pages_needing_ocr"] == 2
        assert meta["page_count"] == 2

    def test_page_count_mismatch_warns_and_numbers_from_library(
        self, monkeypatch, tmp_path, caplog
    ):
        """Design D3: a different per-page length warns; numbers follow ``PageMarkdown.page``."""
        stub = _stub_pdf_inspector(monkeypatch, "body", page_count=3)
        stub.extract_pages_markdown.return_value.pages = [
            _page_markdown(0, "first"),
            _page_markdown(2, "third"),
        ]
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        with caplog.at_level("WARNING", logger="omrs.integrations.pdf.pdf_inspector"):
            documents = PdfInspectorReader().load_data(file=_fake_pdf(tmp_path, "short.pdf"))

        assert [doc.metadata["page"] for doc in documents] == [1, 3]
        assert all(doc.metadata["page_count"] == 3 for doc in documents)
        assert any(
            record.levelname == "WARNING" and "short.pdf" in record.getMessage()
            for record in caplog.records
        )


# ── Fallback chain keeps pages (change pdf-inspector-page-provenance, D4) ──


def _seed_tier(monkeypatch, name: str, pages: list[tuple[str, dict]]) -> None:
    """Seed a fallback tier whose documents carry the given text and metadata."""
    from llama_index.core import Document

    from omrs.integrations.pdf import registry

    class _StubTier:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def load_data(self, file, *args, **kwargs):
            return [Document(text=text, metadata=dict(meta)) for text, meta in pages]

    monkeypatch.setitem(registry._cache, name, _StubTier)


def _rescue_read(monkeypatch, tmp_path) -> list:
    """Read a stubbed 3-page silent-empty PDF (3 pages flagged)."""
    _stub_pdf_inspector(monkeypatch, "", page_count=3, pages_needing_ocr=[1, 2, 3])
    from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

    return PdfInspectorReader().load_data(file=_fake_pdf(tmp_path, "sloman.pdf"))


class TestRescueKeepsPages:
    """Task 3.1: each recovered page stays its own document (design D4)."""

    def test_liteparse_pages_keep_their_numbers(self, monkeypatch, tmp_path):
        """Spec scenario "Recovered pages keep their numbers"."""
        _seed_tier(
            monkeypatch,
            "liteparse",
            [
                ("lite one", {"page": 1, "page_label": "1"}),
                ("", {"page": 2, "page_label": "2"}),
                ("lite three", {"page": 3, "page_label": "3"}),
            ],
        )
        _stub_pypdf_exploding(monkeypatch)

        documents = _rescue_read(monkeypatch, tmp_path)

        assert [doc.text for doc in documents] == ["lite one", "lite three"]
        assert [doc.metadata["page"] for doc in documents] == [1, 3]
        assert [doc.metadata["page_label"] for doc in documents] == ["1", "3"]

    def test_pypdf_pages_are_numbered_by_position(self, monkeypatch, tmp_path):
        """Spec scenario "pypdf pages are numbered by position", not by the PDF's own label."""
        _seed_tier(monkeypatch, "liteparse", [("", {"page": 1, "page_label": "1"})])
        _seed_tier(
            monkeypatch,
            "pypdf",
            [
                ("roman one", {"page_label": "i"}),
                ("", {"page_label": "ii"}),
                ("roman three", {"page_label": "iii"}),
            ],
        )

        documents = _rescue_read(monkeypatch, tmp_path)

        assert [doc.text for doc in documents] == ["roman one", "roman three"]
        assert [doc.metadata["page"] for doc in documents] == [1, 3]
        assert [doc.metadata["page_label"] for doc in documents] == ["1", "3"]

    @pytest.mark.parametrize("tier", ["liteparse", "pypdf"])
    def test_every_recovered_page_carries_evidence_and_diagnostics(
        self, monkeypatch, tmp_path, tier
    ):
        """Each recovered document carries the whole-PDF evidence and the fallback diagnostics."""
        recovered = [("page a", {"page": 1, "page_label": "1"}), ("page b", {"page_label": "x"})]
        if tier == "liteparse":
            _seed_tier(monkeypatch, "liteparse", recovered)
            _stub_pypdf_exploding(monkeypatch)
        else:
            _seed_tier(monkeypatch, "liteparse", [])
            _seed_tier(monkeypatch, "pypdf", recovered)

        documents = _rescue_read(monkeypatch, tmp_path)

        assert len(documents) == 2
        for doc in documents:
            meta = doc.metadata
            assert meta["extraction_fallback_backend"] == tier
            assert meta["pages_needing_ocr"] == 0
            assert meta["pages_needing_ocr_before_fallback"] == 3
            assert meta["pdf_reader"] == "pdf_inspector"
            assert meta["pdf_type"] == "text_based"
            assert meta["page_count"] == 3
            assert meta["file_name"] == "sloman.pdf"

    def test_chain_that_recovers_nothing_emits_one_empty_document(self, monkeypatch, tmp_path):
        """No tier recovers text: one empty document with the original count and no page."""
        _seed_tier(monkeypatch, "liteparse", [("", {"page": 1, "page_label": "1"})])
        _seed_tier(monkeypatch, "pypdf", [("  ", {"page_label": "i"})])

        documents = _rescue_read(monkeypatch, tmp_path)

        assert len(documents) == 1
        assert documents[0].text == ""
        meta = documents[0].metadata
        assert meta["pages_needing_ocr"] == 3
        assert "page" not in meta
        assert "page_label" not in meta
        assert "extraction_fallback_backend" not in meta
