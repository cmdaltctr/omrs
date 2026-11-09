"""The model-token Markdown path builds one splitter per set of splitter inputs.

Profile of 2026-11-08 (pre-exp35-ingest-profile) showed that building a
``MarkdownSplitter`` for every document cost about 0.085 s per file. These tests
pin the reuse and pin the chunks, so reuse cannot change what is indexed.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from llama_index.core import Document
from semantic_text_splitter import MarkdownSplitter

from omrs.core.chunking.model_token import (
    MODEL_AWARE_PATH,
    MarkdownChunkingResolution,
    split_markdown_documents,
)

_RESOLUTION_IDENTITY = {"model": "test/word-level", "revision": "test-revision"}

# Digest of the (text, header_path) pairs that the code produced before the
# splitter was reused (computed 2026-11-09 on the old code, fixture below).
_GOLDEN = {
    "plain": "9e54550194ca086d83c642788b25babea4ac364e3c1add1c10592a62aa9a2a71",
    "prepend": "1e141807164980512fcebf8e48e2d3479dcbbf19ff2c3cdf73d9bfc4d22c2d8d",
}


def _stub_tokenizer():
    """Return a word-level tokenizer whose units are whitespace-ish words."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    return tokenizer


def _resolution() -> MarkdownChunkingResolution:
    return MarkdownChunkingResolution(_stub_tokenizer(), _RESOLUTION_IDENTITY, MODEL_AWARE_PATH)


def _documents() -> list[Document]:
    """Three documents with nested headings, a list and a long paragraph."""
    words = " ".join(f"word{index}" for index in range(60))
    first = f"# Alpha\n\n{words}\n\n## Beta\n\n- one two three\n- four five six\n\n{words}\n"
    second = f"# Gamma\n\nshort body\n\n## Delta\n\n{words}\n\n### Epsilon\n\n{words}\n"
    third = f"Intro line without a heading.\n\n# Zeta\n\n{words}\n\n{words}\n"
    return [Document(text=text) for text in (first, second, third)]


def _digest(nodes: list) -> str:
    rows = [(node.text, node.metadata.get("header_path", "")) for node in nodes]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


class _CountingSplitter:
    """Wraps the real splitter class and counts how often one is built."""

    builds: list[tuple[int, int]] = []

    @classmethod
    def from_huggingface_tokenizer(cls, tokenizer: object, capacity: int, *, overlap: int):
        """Build a real splitter and record its capacity and overlap."""
        cls.builds.append((capacity, overlap))
        return MarkdownSplitter.from_huggingface_tokenizer(tokenizer, capacity, overlap=overlap)


@pytest.fixture
def counting_splitter(monkeypatch: pytest.MonkeyPatch) -> type[_CountingSplitter]:
    """Install a splitter class that records each build, with a fresh log."""
    import semantic_text_splitter

    class _Counting(_CountingSplitter):
        builds: list[tuple[int, int]] = []

    monkeypatch.setattr(semantic_text_splitter, "MarkdownSplitter", _Counting)
    return _Counting


def test_same_settings_build_the_splitter_once(counting_splitter: type[_CountingSplitter]) -> None:
    """Splitting three documents with the same settings builds one splitter."""
    resolution = _resolution()

    split_markdown_documents(_documents(), chunk_size=48, chunk_overlap=0, resolution=resolution)

    assert counting_splitter.builds == [(48, 0)]


def test_a_different_capacity_builds_a_second_splitter(
    counting_splitter: type[_CountingSplitter],
) -> None:
    """A second capacity is a separate splitter; the first is not reused for it."""
    resolution = _resolution()

    split_markdown_documents(_documents(), chunk_size=48, chunk_overlap=0, resolution=resolution)
    split_markdown_documents(_documents(), chunk_size=32, chunk_overlap=0, resolution=resolution)

    assert counting_splitter.builds == [(48, 0), (32, 0)]


def test_a_different_overlap_builds_a_second_splitter(
    counting_splitter: type[_CountingSplitter],
) -> None:
    """A second overlap is a separate splitter."""
    resolution = _resolution()

    split_markdown_documents(_documents(), chunk_size=48, chunk_overlap=0, resolution=resolution)
    split_markdown_documents(_documents(), chunk_size=48, chunk_overlap=8, resolution=resolution)

    assert counting_splitter.builds == [(48, 0), (48, 8)]


@pytest.mark.parametrize("heading_prepend", [False, True], ids=["plain", "prepend"])
def test_reuse_leaves_the_chunks_unchanged(heading_prepend: bool) -> None:
    """The chunks equal the output recorded from the code that built one per document."""
    nodes = split_markdown_documents(
        _documents(),
        chunk_size=40,
        chunk_overlap=4,
        resolution=_resolution(),
        heading_prepend=heading_prepend,
    )

    assert _digest(nodes) == _GOLDEN["prepend" if heading_prepend else "plain"]
