"""Page-provenance contract (fix-embedding-and-structure-fidelity-1).

Spec: openspec/changes/fix-embedding-and-structure-fidelity-1/specs/
pdf-reader/spec.md — "Page provenance is honest per reader".

Readers that can observe page boundaries SHALL emit ``page_label`` (the
key retrieval reads) as a string alongside the existing integer ``page``.
``pdf_inspector`` emits one document per page with the same keys (change
pdf-inspector-page-provenance); its whole-document fallback cannot know
the page, so it MUST emit nothing rather than a placeholder while still
reporting ``page_count``. The registry descriptor exposes
the capability (``page_provenance``) and the configuration guide's
per-reader matrix must agree with it (task 6.5).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_GUIDE = _REPO_ROOT / "docs" / "guides" / "configuration.md"


# ── Stub plumbing for pypdfium2 (not installed in the base venv) ───────


def _install_fake_pypdfium2(monkeypatch: pytest.MonkeyPatch, page_texts: list[str]) -> None:
    """Install a fake ``pypdfium2`` module in ``sys.modules``.

    The stub mirrors the adapter's narrow API surface (``PdfDocument``
    supporting ``len``, indexing, and ``close``; pages exposing
    ``get_textpage().get_text_range()``) so the REAL adapter code runs.
    ``monkeypatch.setitem`` restores any prior entry on teardown.
    """
    import types

    class _FakeTextPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_text_range(self) -> str:
            return self._text

    class _FakePdfPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_textpage(self) -> _FakeTextPage:
            return _FakeTextPage(self._text)

    class _FakePdfDocument:
        def __init__(self, path: str) -> None:
            self._pages = [_FakePdfPage(text) for text in page_texts]

        def __len__(self) -> int:
            return len(self._pages)

        def __getitem__(self, index: int) -> _FakePdfPage:
            return self._pages[index]

        def close(self) -> None:
            return None

    stub = types.ModuleType("pypdfium2")
    stub.PdfDocument = _FakePdfDocument  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pypdfium2", stub)


# ── Task 1.4 / 6.1: liteparse and pypdfium2 emit page_label ───────────


class TestLiteParsePageLabel:
    """liteparse knows the page number; it must say so (spec scenario)."""

    def test_emits_string_page_label_alongside_integer_page(self, fixtures_dir: Path) -> None:
        """Each emitted document carries a string page_label next to int page."""
        from omrs.integrations.pdf.liteparse import LiteParseReader

        documents = LiteParseReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert documents, "smoke_text.pdf must parse to at least one page document"
        for doc in documents:
            meta = doc.metadata
            assert "page" in meta, f"integer page missing: {sorted(meta)}"
            assert isinstance(meta["page"], int)
            assert "page_label" in meta, (
                f"page_label missing (page_provenance is declared true): {sorted(meta)}"
            )
            assert isinstance(meta["page_label"], str)
            # pypdf's existing format: the 1-based page number as a string.
            assert meta["page_label"] == str(meta["page"])


class TestPypdfium2PageLabel:
    """pypdfium2 paginates per page; it must emit page_label (spec scenario)."""

    def test_emits_string_page_label_alongside_integer_page(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Each emitted page document carries a string page_label next to int page."""
        _install_fake_pypdfium2(
            monkeypatch,
            [
                "First page text with enough content to survive chunking.",
                "Second page text with enough content to survive chunking.",
            ],
        )
        from omrs.integrations.pdf.pypdfium import PyPDFium2Reader

        pdf = tmp_path / "two_page.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        documents = PyPDFium2Reader().load_data(file=pdf)

        assert len(documents) == 2
        for index, doc in enumerate(documents, start=1):
            meta = doc.metadata
            assert meta["page"] == index
            assert isinstance(meta["page"], int)
            assert "page_label" in meta, (
                f"page_label missing (page_provenance is declared true): {sorted(meta)}"
            )
            assert isinstance(meta["page_label"], str)
            assert meta["page_label"] == str(index)


class TestAutoChainPreservesPageLabel:
    """A chunk retrieved through the ``auto`` chain keeps its page_label."""

    async def test_chunk_retrieved_through_auto_keeps_page_label(
        self,
        monkeypatch: pytest.MonkeyPatch,
        effective_settings,
        fixtures_dir: Path,
    ) -> None:
        """auto → pypdfium2 → stored chunk metadata carries page_label.

        Spec scenario "pypdfium2 emits page_label": a chunk retrieved
        through the ``auto`` chain MUST preserve it. liteparse is poisoned
        so the capability probe falls through to the stubbed pypdfium2.
        """
        _install_fake_pypdfium2(
            monkeypatch,
            ["Auto-chain page text with enough words to form a chunk. " * 4],
        )
        monkeypatch.setitem(sys.modules, "liteparse", None)

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.vectordb import get_default_store

        settings = effective_settings(pdf_reader="auto", extraction_mode="disabled")
        result = await ingest_path_async(
            str(fixtures_dir / "smoke_text.pdf"),
            collection_name="auto_page_label",
            effective_settings=settings,
        )

        assert result["status"] == "ok", result
        assert result["chunks_created"] >= 1

        payload = get_default_store().fetch_all("auto_page_label", ["metadatas"])
        assert payload, "no chunks stored"
        labels = {meta.get("page_label") for meta in payload["metadatas"]}
        # Retrieval reads ``page_label`` straight from stored metadata
        # (core/retrieval/dense.py) — preserved means present and stringly.
        assert labels == {"1"}


# ── pdf_inspector: honest absence (spec scenario) ──────────────────────


class TestPdfInspectorEmitsPages:
    """pdf_inspector emits page documents (change pdf-inspector-page-provenance).

    It reports ``page`` and ``page_label`` when its per-page extraction
    succeeds, and no page at all, never a placeholder, when it falls back
    to the whole-document Markdown. ``page_count`` is present either way.
    """

    def test_smoke_pdf_gives_page_one(self, fixtures_dir: Path) -> None:
        """Spec scenario "pdf_inspector emits page_label"."""
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        documents = PdfInspectorReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert len(documents) == 1
        meta = documents[0].metadata
        assert meta["page"] == 1
        assert meta["page_label"] == "1"
        assert meta["page_count"] == 1

    def test_per_page_failure_reports_no_page(
        self, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec scenario "pdf_inspector reports no page": absent, never fabricated."""
        import pdf_inspector

        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        def _fail(path: str, *args: object, **kwargs: object) -> object:
            raise RuntimeError("per-page extraction failed")

        monkeypatch.setattr(pdf_inspector, "extract_pages_markdown", _fail)

        documents = PdfInspectorReader().load_data(file=fixtures_dir / "smoke_text.pdf")

        assert len(documents) == 1
        meta = documents[0].metadata
        assert "page_label" not in meta, (
            f"a whole-document fallback cannot name a page; fabricating one is forbidden: "
            f"{sorted(meta)}"
        )
        assert "page" not in meta
        assert meta["page_count"] == 1
        assert "Smoke Test Document" in documents[0].get_content()

    def test_mixed_pdf_text_page_is_page_one(self, fixtures_dir: Path) -> None:
        """A real 2-page PDF: the text page is page 1; the image-only page emits nothing."""
        from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader

        pdf = fixtures_dir / "pdf_baseline" / "evaluation" / "eval_mixed.pdf"
        documents = PdfInspectorReader().load_data(file=pdf)

        assert [doc.metadata["page"] for doc in documents] == [1]
        assert [doc.metadata["page_label"] for doc in documents] == ["1"]
        assert documents[0].metadata["page_count"] == 2
        assert "Page One" in documents[0].get_content()


# ── Task 6.5: the configuration guide and the registry agree ──────────


class TestDocsAndRegistryAgree:
    """The documented page-provenance matrix mirrors ``registry.describe()``."""

    @staticmethod
    def _matrix_rows() -> dict[str, tuple[str, bool]]:
        """Parse the per-reader matrix out of the configuration guide.

        Returns ``{reader: (text_format, page_provenance)}`` from rows like
        ``| `pypdf` | `plain` | Yes — per-page |`` inside the PDF reading
        section.
        """
        text = _CONFIG_GUIDE.read_text(encoding="utf-8")
        rows: dict[str, tuple[str, bool]] = {}
        pattern = re.compile(
            r"^\|\s*`(?P<reader>[a-z0-9_]+)`\s*"
            r"\|\s*`(?P<fmt>plain|markdown)`\s*"
            r"\|\s*(?P<page>Yes|No)\b",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            rows[match.group("reader")] = (
                match.group("fmt"),
                match.group("page") == "Yes",
            )
        return rows

    def test_every_registered_reader_has_a_matrix_row(self) -> None:
        """The matrix covers exactly the registered concrete readers."""
        from omrs.integrations.pdf import registry

        rows = self._matrix_rows()
        assert set(rows) == set(registry.available()), (
            f"configuration.md page-provenance matrix rows {sorted(rows)} do not "
            f"match registered readers {registry.available()}"
        )

    def test_matrix_agrees_with_registry_declarations(self) -> None:
        """Each row's format and page capability match ``describe()``."""
        from omrs.integrations.pdf import registry

        rows = self._matrix_rows()
        assert rows, "no page-provenance matrix found in docs/guides/configuration.md"
        for reader, (text_format, page_provenance) in rows.items():
            described = registry.describe(reader)
            assert described["text_format"] == text_format, reader
            assert described["page_provenance"] is page_provenance, reader


# ── End to end: pdf_inspector chunks keep their pages (task 6.1) ──────


def _bag_of_words_embedding():
    """Return a unit-norm hashed bag-of-words embedder (test only).

    The suite's default mock embedder returns one constant vector, so a
    dense search cannot tell two pages apart. Shared words give a higher
    cosine score here, which is all the page check needs.
    """
    import hashlib
    import math

    from llama_index.core.embeddings import MockEmbedding

    def vector(text: str, dim: int) -> list[float]:
        counts = [0.0] * dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            counts[int.from_bytes(digest, "big") % dim] += 1.0
        norm = math.sqrt(math.fsum(x * x for x in counts)) or 1.0
        return [x / norm for x in counts]

    class _BagOfWords(MockEmbedding):
        model_name: str = "test-bag-of-words-page-provenance"

        def _get_query_embedding(self, query: str) -> list[float]:
            return vector(query, self.embed_dim)

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return vector(query, self.embed_dim)

        def _get_text_embedding(self, text: str) -> list[float]:
            return vector(text, self.embed_dim)

    return _BagOfWords(embed_dim=256)


class TestPdfInspectorPagesEndToEnd:
    """Ingest a 2-page PDF with ``pdf_inspector``; every chunk names its page."""

    async def test_two_page_pdf_chunks_and_search_keep_pages(
        self,
        monkeypatch: pytest.MonkeyPatch,
        effective_settings,
        fixtures_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Spec scenario "A chunk keeps its page"."""
        from llama_index.core import Settings as LlamaIndexSettings
        from pypdf import PdfReader, PdfWriter

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval.dense import _cached_query_embedding
        from omrs.core.retrieval.pipeline import search
        from omrs.core.vectordb import get_default_store

        # Page 1 is smoke_text.pdf, page 2 is eval_clean_text.pdf: no new binary.
        writer = PdfWriter()
        for source in (
            fixtures_dir / "smoke_text.pdf",
            fixtures_dir / "pdf_baseline" / "evaluation" / "eval_clean_text.pdf",
        ):
            writer.add_page(PdfReader(source).pages[0])
        pdf = tmp_path / "two_pages.pdf"
        writer.write(pdf)

        monkeypatch.setattr(LlamaIndexSettings, "embed_model", _bag_of_words_embedding())
        _cached_query_embedding.cache_clear()
        settings = effective_settings(pdf_reader="pdf_inspector", extraction_mode="disabled")
        collection = "pdf_inspector_pages"

        result = await ingest_path_async(
            str(pdf), collection_name=collection, effective_settings=settings
        )

        assert result["status"] == "ok", result
        payload = get_default_store().fetch_all(collection, ["documents", "metadatas"])
        rows = list(zip(payload["documents"], payload["metadatas"], strict=True))
        assert rows, "no chunks stored"
        assert {meta.get("page_label") for _, meta in rows} == {"1", "2"}
        for text, meta in rows:
            page_one = "Smoke Test Document" in text
            page_two = "OMRS-EV-0042" in text or "held-out" in text
            assert not (page_one and page_two), f"a chunk crosses the page break: {text!r}"
            if page_one:
                assert meta["page_label"] == "1"
            if page_two:
                assert meta["page_label"] == "2"

        _cached_query_embedding.cache_clear()
        hits = search(
            "identifier sample OMRS-EV-0042 held-out retrieval",
            top_k=3,
            similarity_threshold=0.0,
            rerank=False,
            hybrid=False,
            collection_name=collection,
            effective_settings=settings,
        )
        assert hits, "dense search returned nothing"
        assert hits[0]["page_label"] == "2"


# ── Normalisation runs per page (task 6.2, design D6) ─────────────────


class TestNormalisationRunsPerPage:
    """Reader-output normalisation cleans each page document and keeps its page."""

    async def test_underline_tags_go_and_the_page_stays(
        self,
        monkeypatch: pytest.MonkeyPatch,
        effective_settings,
        tmp_path: Path,
    ) -> None:
        """A page document with ``<u>HEADER</u>`` chunks without ``<u>``, still on page 2."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from omrs.core.ingestion.chunker import read_and_chunk_file_async
        from omrs.core.ingestion.normalise import NORMALISER_VERSION

        pages = ["# Opening\n\nFirst page body text.", "<u>HEADER</u>\n\nSecond page body text."]
        stub = MagicMock()
        result = stub.process_pdf.return_value
        result.markdown = "\n\n".join(pages)
        result.pdf_type = "text_based"
        result.confidence = 1.0
        result.page_count = 2
        result.pages_needing_ocr = []
        stub.extract_pages_markdown.return_value = SimpleNamespace(
            pages=[
                SimpleNamespace(page=index, markdown=text, needs_ocr=False, ocr_reason=None)
                for index, text in enumerate(pages)
            ],
            pages_needing_ocr=[],
        )
        monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
        pdf = tmp_path / "underlined.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        settings = effective_settings(
            pdf_reader="pdf_inspector",
            extraction_mode="disabled",
            ocr_fallback_enabled=False,
            normalise_reader_output=True,
        )

        nodes = await read_and_chunk_file_async(pdf, settings=settings)

        assert NORMALISER_VERSION == 2
        header = [node for node in nodes if "HEADER" in node.get_content()]
        assert header, [node.get_content() for node in nodes]
        for node in header:
            assert "<u>" not in node.get_content()
            assert node.metadata["page"] == 2
            assert node.metadata["page_label"] == "2"
        assert {node.metadata["page"] for node in nodes} == {1, 2}
