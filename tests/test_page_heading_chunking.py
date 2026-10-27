"""Heading context across page documents in both Markdown chunking paths.

Design D11 and task 6a.3: when one source arrives as page documents, every
chunk's ``header_path`` equals the path that whole-document chunking gives
at the same position, provided the page texts joined in order equal the
whole-document text. Both the legacy path (``MarkdownNodeParser``) and the
model-token path are checked.
"""

from __future__ import annotations

import pytest
from llama_index.core import Document

from omrs.core.chunking import model_token
from omrs.core.chunking.sentence import chunk_sentence_file_async
from omrs.core.settings import ChunkingBlock, EffectiveSettings, EmbeddingBlock, MetadataBlock

_SOURCE = "/docs/paper.pdf"

# Three pages whose sections run across the page breaks. Each body sentence
# is unique, so a chunk can be located in the whole-document text.
_PAGES = (
    "# Intro\n\nalpha one opens the paper.\n\n## Background\n\nbravo two sets context.\n\n",
    "charlie three continues background.\n\n## Methods\n\ndelta four describes methods.\n\n"
    "### Data\n\necho five lists data.\n\n",
    "foxtrot six continues data.\n\n# Results\n\ngolf seven reports results.\n\n",
)
_WHOLE = "".join(_PAGES)


def _page_documents(pages: tuple[str, ...] = _PAGES) -> list[Document]:
    """Return one synthetic page document per page text."""
    return [
        Document(
            text=text,
            metadata={"page": number, "page_label": str(number), "file_path": _SOURCE},
        )
        for number, text in enumerate(pages, start=1)
    ]


def _whole_document() -> list[Document]:
    """Return the same text as one whole-document read."""
    return [Document(text=_WHOLE, metadata={"file_path": _SOURCE})]


def _path_of(nodes: list, needle: str) -> str:
    """Return the ``header_path`` of the one node whose text holds ``needle``."""
    matches = [node for node in nodes if needle in node.get_content()]
    assert len(matches) == 1, f"expected one chunk holding {needle!r}, got {len(matches)}"
    return matches[0].metadata.get("header_path")


# ── Legacy path: MarkdownNodeParser + SentenceSplitter ────────────────────


async def _legacy_chunks(documents: list[Document], effective_settings) -> list:
    """Chunk through the legacy Markdown path (empty tokenizer identity)."""
    return await chunk_sentence_file_async(
        documents,
        _SOURCE,
        True,
        settings=effective_settings(extraction_mode="disabled"),
    )


@pytest.mark.asyncio
async def test_legacy_page_chunks_match_whole_document_paths(effective_settings) -> None:
    """Every page chunk has the path whole-document chunking gives there."""
    paged = await _legacy_chunks(_page_documents(), effective_settings)
    whole = await _legacy_chunks(_whole_document(), effective_settings)

    for node in paged:
        text = node.get_content().strip()
        holders = [w for w in whole if text in w.get_content()]
        assert len(holders) == 1, f"no single whole-document chunk holds {text!r}"
        assert node.metadata["header_path"] == holders[0].metadata["header_path"], text


@pytest.mark.asyncio
async def test_legacy_first_chunk_of_next_page_keeps_open_section(effective_settings) -> None:
    """Body text that opens page 2 stays inside ``Intro > Background``.

    The legacy format lists the parents of the section heading, as
    LlamaIndex does for the whole document, so the path is ``/Intro/``.
    """
    paged = await _legacy_chunks(_page_documents(), effective_settings)

    assert _path_of(paged, "charlie three") == "/Intro/"
    assert _path_of(paged, "foxtrot six") == "/Intro/Methods/"
    assert _path_of(paged, "delta four") == "/Intro/"
    assert _path_of(paged, "echo five") == "/Intro/Methods/"
    assert _path_of(paged, "golf seven") == "/"


@pytest.mark.asyncio
async def test_legacy_gap_in_pages_ends_inherited_path(effective_settings) -> None:
    """A missing page 2 means page 3 starts with no heading context."""
    documents = _page_documents()
    documents[2].metadata.update({"page": 4, "page_label": "4"})

    paged = await _legacy_chunks(documents, effective_settings)

    assert _path_of(paged, "foxtrot six") == "/"


# ── Model-token path ──────────────────────────────────────────────────────


def _model_token_settings(monkeypatch: pytest.MonkeyPatch) -> EffectiveSettings:
    """Install a word-level tokenizer and build settings that resolve to it."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    monkeypatch.setattr(model_token, "load_tokenizer", lambda *_args: tokenizer)
    return EffectiveSettings(
        chunking=ChunkingBlock(markdown_chunk_size=8, chunk_overlap=0),
        embedding=EmbeddingBlock(tokenizer_model="test/word-level", tokenizer_revision="test"),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )


async def _model_token_chunks(documents: list[Document], settings: EffectiveSettings) -> list:
    """Chunk through the model-token Markdown path."""
    return await chunk_sentence_file_async(documents, _SOURCE, True, settings=settings)


def _whole_path_at(offset: int) -> str:
    """Return the model-token path whole-document chunking gives at ``offset``."""
    headings = model_token._heading_positions(_WHOLE)
    return model_token._header_path_at(headings, offset)


@pytest.mark.asyncio
async def test_model_token_page_chunks_match_whole_document_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every page chunk has the path whole-document chunking gives there."""
    settings = _model_token_settings(monkeypatch)

    paged = await _model_token_chunks(_page_documents(), settings)

    assert paged
    for node in paged:
        text = node.get_content()
        assert _WHOLE.count(text) == 1, f"chunk {text!r} is not unique in the source"
        expected = _whole_path_at(_WHOLE.index(text))
        assert node.metadata.get("header_path", "") == expected, text


@pytest.mark.asyncio
async def test_model_token_first_chunk_of_next_page_keeps_open_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Body text that opens a page carries the full open heading path."""
    settings = _model_token_settings(monkeypatch)

    paged = await _model_token_chunks(_page_documents(), settings)

    assert _path_of(paged, "charlie three") == "/Intro/Background/"
    assert _path_of(paged, "foxtrot six") == "/Intro/Methods/Data/"
    assert _path_of(paged, "golf seven") == "/Results/"


@pytest.mark.asyncio
async def test_model_token_heading_prepend_uses_inherited_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With heading prepend on, the inherited path is the prefix as well."""
    settings = _model_token_settings(monkeypatch)
    settings = settings.model_copy(
        update={
            "chunking": ChunkingBlock(
                markdown_chunk_size=16, chunk_overlap=0, markdown_heading_prepend=True
            )
        }
    )

    paged = await _model_token_chunks(_page_documents(), settings)

    holders = [node for node in paged if "charlie three" in node.get_content()]
    assert len(holders) == 1
    assert holders[0].metadata["header_path"] == "/Intro/Background/"
    assert holders[0].get_content().startswith("[/Intro/Background/] ")


@pytest.mark.asyncio
async def test_model_token_two_sources_never_share_a_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page 2 of another source does not inherit this source's headings."""
    settings = _model_token_settings(monkeypatch)
    documents = _page_documents()
    documents[1].metadata["file_path"] = "/docs/other.pdf"

    paged = await _model_token_chunks(documents, settings)

    assert not _path_of(paged, "charlie three")
