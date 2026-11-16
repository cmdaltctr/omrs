"""The ingest prepares the native full-text index (design D26).

A native query never writes, so ``ingest_path_async`` creates the FTS
index and folds unindexed rows into it at the end of every run whose
resolved sparse backend is ``native``.
"""

from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path

import pytest
from llama_index.core.embeddings import MockEmbedding

from omrs.core.ingestion import ingest_path_async
from omrs.core.vectordb.base import VectorStore
from omrs.core.vectordb.lancedb.fts import fts_index_stats
from omrs.core.vectordb.lancedb.store import LanceVectorStore


class _UnitEmbedding(MockEmbedding):
    """MockEmbedding with unit-norm vectors, so the norm guard accepts it."""

    def _get_vector(self) -> list[float]:
        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector] if norm else list(vector)


async def _ingest(path: Path, store: LanceVectorStore, settings) -> dict:
    return await ingest_path_async(
        str(path),
        collection_name="docs",
        store=store,
        embed_model=_UnitEmbedding(embed_dim=8, model_name="mock"),
        effective_settings=settings,
    )


def _stats(store: LanceVectorStore):
    return fts_index_stats(store._open_table("docs"))


@pytest.fixture
def corpus(tmp_path: Path, sample_md: Path) -> Path:
    folder = tmp_path / "corpus"
    folder.mkdir()
    shutil.copy(sample_md, folder / "first.md")
    return folder


@pytest.fixture
def native(effective_settings):
    return effective_settings(hybrid_sparse_backend="native")


async def test_native_ingest_builds_and_refreshes_the_index(
    tmp_path: Path, corpus: Path, native
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    await _ingest(corpus, store, native)
    first = _stats(store)
    assert first is not None and first[0] > 0 and first[1] == 0

    (corpus / "second.md").write_text("# Second\n\nA zephyr paragraph about kites.\n")
    await _ingest(corpus, store, native)
    second = _stats(store)
    assert second is not None and second[1] == 0
    assert second[0] > first[0]


async def test_ingest_that_writes_nothing_prepares_existing_collection(
    tmp_path: Path, corpus: Path, native, effective_settings
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    await _ingest(corpus, store, effective_settings(hybrid_sparse_backend="bm25"))
    assert _stats(store) is None

    result = await _ingest(corpus, store, native)

    assert result["files_indexed"] == 0 and result["files_skipped_unchanged"] == 1
    stats = _stats(store)
    assert stats is not None and stats[1] == 0


async def test_bm25_ingest_creates_no_index(
    tmp_path: Path, corpus: Path, effective_settings
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    await _ingest(corpus, store, effective_settings(hybrid_sparse_backend="bm25"))
    assert _stats(store) is None


async def test_prepare_failure_warns_and_keeps_the_result(
    tmp_path: Path, corpus: Path, native, monkeypatch, caplog
) -> None:
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))

    def _boom(_collection_name: str) -> None:
        raise RuntimeError("index build exploded")

    monkeypatch.setattr(store, "prepare_native_sparse", _boom)
    with caplog.at_level(logging.WARNING):
        result = await _ingest(corpus, store, native)

    assert result["status"] == "ok" and result["files_indexed"] == 1
    assert "warnings" not in result
    assert any("index build exploded" in r.getMessage() for r in caplog.records)


def test_base_store_prepare_is_a_no_op() -> None:
    assert VectorStore.prepare_native_sparse(object(), "docs") is None  # type: ignore[arg-type]


def test_chroma_store_prepare_does_nothing() -> None:
    pytest.importorskip(
        "chromadb", reason="chroma extra not installed; runs in the Coverage CI job"
    )
    from omrs.core.vectordb.chroma.store import ChromaVectorStore

    assert ChromaVectorStore().prepare_native_sparse("documents") is None
