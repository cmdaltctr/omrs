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

# Pinned from the code before this change.
CODE_DEFAULT_PDF = "b3ec63104c8708615f988cbce02882c19a851ffff188d2bc06b908fc97410c3c"
PDF_INSPECTOR_PDF = "1f06f234b4cec7f3bd202f74839ff276e56c055e26a0d3a0392ef42c60fa476d"
PDF_INSPECTOR_TEXT = "3e73e90882769ba455a46d3e56663fc83c47b29396dc31fc33d98cc550dd4a06"
LITEPARSE_PDF = "b42e1f367efe35e3db7c075d0e02d9eb9d858151a13a3fd7826f5f5be327a852"
PYPDF_PDF = "5373263b47c1e596dc677d2ee0a03e49dcf56dce84f8fb9e12c82ed93d866b45"

DEFAULT_LIST = ("pdf_inspector", "liteparse", "pypdf")


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
