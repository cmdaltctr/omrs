"""Reader list in the source index identity (ordered-reader-and-ocr-lists, task 2.3, design D5).

The pinned digests were computed under pytest (the conftest mock embedder is
part of the identity) on commit a87435a1, before the reader list reached the
identity: ``build_index_identity`` on ``EffectiveSettings`` with extraction
disabled and an empty tokenizer identity, 512/100 chunks.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.core.ingestion import source_state
from omrs.core.ingestion.reader_identity import reader_list_payload
from omrs.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock
from omrs.integrations.pdf import page_routing

# Pinned from the code before the reader list change.
# Re-pinned on 6 November 2026 (change local-ocr-per-backend-cuts): schema 7 to 8
# moved every digest. The text pin also lost ``ocr_routing.local_tier`` (default
# cut 0.9). The PDF pins also gained ``parser.local_ocr_backends`` (the default
# backend at cut 0.92, model left unresolved by the fixture below).
CODE_DEFAULT_PDF = "be86b42e3153d7ad09710bdf17bb6cfaa84b56fe747b0537ef83b0352049e494"
PDF_INSPECTOR_PDF = "2da39acb3a7781989f510e165ff6f4b3344859b1f2c6fdc93f5892d3387009e6"
PDF_INSPECTOR_TEXT = "d73adaba8611d4289c40313c34a1cb8f3d74a2e7b3093aaffe7a417a417c811c"
LITEPARSE_PDF = "0eea2f64a894b3f2671ac6575fb0656ffacad9d0b7dca34793c0d14a62425383"
PYPDF_PDF = "74aff94e4d38cd024c221077de5313134690842e3f1ba8b5b02752b1434f2e8b"

DEFAULT_LIST = ("pdf_inspector", "liteparse", "pypdf")


@pytest.fixture(autouse=True)
def _unresolved_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash with the local OCR model unresolved: the real probe depends on the host runtime."""
    page_routing.reset_local_model_resolution()
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings, backend="x": None
    )


def digest(content_type: str = "application/pdf", **overrides: Any) -> str:
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        embedding=EmbeddingBlock(tokenizer_model="", tokenizer_revision=""),
        **overrides,
    )
    return source_state.build_index_identity(
        settings,
        content_type=content_type,
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2 if content_type == "application/pdf" else None,
    )


def test_the_code_default_keeps_its_digest() -> None:
    assert digest() == CODE_DEFAULT_PDF


def test_the_old_key_and_the_equal_list_give_the_pinned_digest() -> None:
    """Mutation check: dropping ``pdf_reader`` from the payload fails this test."""
    assert digest(pdf_reader="pdf_inspector") == PDF_INSPECTOR_PDF
    assert digest(pdf_reader="pdf_inspector", pdf_readers=DEFAULT_LIST) == PDF_INSPECTOR_PDF


@pytest.mark.parametrize(("reader", "pinned"), [("liteparse", LITEPARSE_PDF), ("pypdf", PYPDF_PDF)])
def test_a_single_reader_list_keeps_the_old_key_and_value(reader: str, pinned: str) -> None:
    assert digest(pdf_reader=reader, pdf_readers=(reader,)) == pinned


def test_a_list_equal_to_an_expansion_adds_nothing_to_the_payload() -> None:
    settings = EffectiveSettings(pdf_reader="pdf_inspector", pdf_readers=DEFAULT_LIST)
    assert reader_list_payload(settings) == {}


def test_a_different_list_adds_the_full_list_to_the_payload() -> None:
    settings = EffectiveSettings(
        pdf_reader="pdf_inspector", pdf_readers=("pdf_inspector", "pypdfium2")
    )
    assert reader_list_payload(settings) == {"pdf_readers": ["pdf_inspector", "pypdfium2"]}


def test_a_different_list_moves_the_pdf_digest() -> None:
    changed = digest(pdf_reader="pdf_inspector", pdf_readers=("pdf_inspector", "pypdfium2"))
    assert changed != PDF_INSPECTOR_PDF
    assert changed != digest(pdf_reader="pdf_inspector", pdf_readers=("pdf_inspector", "pypdf"))


def test_the_order_of_a_different_list_counts() -> None:
    forward = digest(pdf_reader="pypdf", pdf_readers=("pypdf", "pdf_inspector"))
    backward = digest(pdf_reader="pdf_inspector", pdf_readers=("pdf_inspector", "pypdf"))
    assert forward != backward


def test_a_different_list_leaves_other_sources_alone() -> None:
    """A text source carries no reader revision, so the list must not reach it."""
    plain = digest("text/plain", pdf_reader="pdf_inspector")
    assert plain == PDF_INSPECTOR_TEXT
    custom = digest(
        "text/plain", pdf_reader="pdf_inspector", pdf_readers=("pdf_inspector", "pypdfium2")
    )
    assert custom == PDF_INSPECTOR_TEXT
