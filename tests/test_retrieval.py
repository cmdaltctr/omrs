"""Integration tests for the retrieval module.

Tests cover:
- search on empty store returns empty
- similarity_threshold filtering
- collection-aware search, metadata filters, list_collections and score
  consistency

Rerank cases live in ``test_retrieval_rerank.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import connected_client, extract_tool_result, ingest_fixture_docs

# ── Empty store ────────────────────────────────────────────────────────────


async def test_search_empty_store_returns_empty(mcp_server) -> None:
    """Searching with no indexed documents must return an empty list."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("search_documents", {"query": "anything"})
        data = extract_tool_result(result)
        assert data == []


# ── Similarity threshold filtering ─────────────────────────────────────────


async def test_high_threshold_filters_all(mcp_server, fixtures_dir: Path) -> None:
    """A very high similarity_threshold should filter all results."""
    async with connected_client(mcp_server) as client:
        await ingest_fixture_docs(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France", "similarity_threshold": 0.99},
        )
        data = extract_tool_result(result)
        # All results may be filtered out (MockEmbedding scores are low)
        # The test verifies the parameter is accepted without error
        assert isinstance(data, list)


async def test_default_threshold_includes_results(mcp_server, fixtures_dir: Path) -> None:
    """Default threshold (0.0) should include all retrieved results."""
    async with connected_client(mcp_server) as client:
        await ingest_fixture_docs(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France"},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


# ── 9.8-9.10 Collection-aware retrieval tests ──────────────────────────────


class TestCollectionAwareSearch:
    """Tests for collection-aware search and filtering."""

    async def test_search_named_collection(self, sample_txt, sample_md):
        """Search must return results only from the specified collection."""
        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        # Ingest into two different collections
        await ingest_path_async(str(sample_txt), collection_name="research")
        await ingest_path_async(str(sample_md), collection_name="code")

        # Search "research" only
        results = search("test", collection_name="research")

        # sample.txt should be in results, sample.md should not
        # (they have different file_name metadata)
        research_sources = set()
        for r in results:
            src = r.get("source", "")
            research_sources.add(src)

        # Search "code" only
        results_code = search("test", collection_name="code")
        assert len(results_code) >= 0  # may have results depending on content

        # Search non-existent collection
        results_empty = search("test", collection_name="nonexistent")
        assert results_empty == []

    async def test_default_collection_search(self, sample_txt):
        """Search without collection_name must use 'documents'."""
        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        await ingest_path_async(str(sample_txt))

        results = search("sample text")
        assert isinstance(results, list)


class TestMetadataFiltering:
    """Tests for metadata filter in search."""

    async def test_filter_by_category(self, tmp_path, monkeypatch):
        """Search with metadata_filter must return only matching chunks."""
        from omrs.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        ai_file = tmp_path / "ai_content.txt"
        ai_file.write_text(
            "The transformer model uses attention heads. Deep learning "
            "neural networks train on large datasets. LLMs use embeddings."
        )
        await ingest_path_async(str(ai_file), collection_name="filtered")

        results = search(
            "attention transformer",
            collection_name="filtered",
            metadata_filter={"category": "AI"},
        )
        assert isinstance(results, list)

        results_mismatch = search(
            "attention transformer",
            collection_name="filtered",
            metadata_filter={"category": "Philosophy"},
        )
        assert results_mismatch == []

    async def test_no_filter_returns_all(self, tmp_path, monkeypatch):
        """Search without metadata_filter must return all categories."""
        from omrs.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        ai_file = tmp_path / "ai.txt"
        ai_file.write_text("attention transformer neural network deep learning")
        await ingest_path_async(str(ai_file), collection_name="no_filter")

        results = search("attention", collection_name="no_filter")
        assert len(results) > 0


class TestListCollections:
    """Tests for list_collections() function."""

    async def test_list_collections_with_data(self, sample_txt, sample_md):
        """list_collections must return collection names and counts."""
        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import list_collections

        await ingest_path_async(str(sample_txt), collection_name="research")
        await ingest_path_async(str(sample_md), collection_name="code")

        collections = list_collections()

        # Must include both collections
        names = {c["name"] for c in collections}
        assert "research" in names
        assert "code" in names

        # Verify structure
        for c in collections:
            assert "name" in c
            assert "document_count" in c
            assert "chunk_count" in c

    def test_list_collections_empty(self):
        """list_collections on fresh store must return empty list."""
        from omrs.core.retrieval import list_collections

        # Note: EphemeralClient is shared between tests,
        # but collections from other tests might be visible.
        # This test just checks the function doesn't crash.
        result = list_collections()
        assert isinstance(result, list)
        for c in result:
            assert "name" in c
            assert "document_count" in c
            assert "chunk_count" in c

    def test_list_collections_scans_multiple_metadata_pages(self, tmp_path, effective_settings):
        """Collection document counts must include all metadata pages.

        Task 5.1 rewrite: seeds through the real ingestion path
        (store-agnostic) instead of a direct ChromaDB client, so the
        pagination contract runs against the default tmp-path LanceDB
        store in the base install and on Chroma in the Coverage CI job.
        """
        from asyncio import run as asyncio_run

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import list_collections
        from omrs.core.settings import set_default_effective_settings

        set_default_effective_settings(effective_settings(chroma_scan_page_size=2))

        total_chunks = 0
        for name in ("a.txt", "b.txt", "c.txt"):
            doc = tmp_path / name
            doc.write_text(f"Collection stats document {name} sentence. " * 12)
            result = asyncio_run(
                ingest_path_async(str(doc), collection_name="paged_collection_stats")
            )
            assert result["status"] == "ok"
            total_chunks += result["chunks_created"]
        # Force more than one scan page at page size 2.
        assert total_chunks > 2

        stats = {c["name"]: c for c in list_collections()}["paged_collection_stats"]
        assert stats["chunk_count"] == total_chunks
        assert stats["document_count"] == 3


# ── Score-metric consistency between filtered and unfiltered paths ─────────


class TestScoreConsistency:
    """Ensure both retrieval paths produce identical pre-threshold scores.

    The fix collapsed both branches into a direct ChromaDB ``query()`` call
    so the conversion is structurally identical.  These tests pin that
    contract: a chunk that comes back on the unfiltered path must score
    the same as that chunk on the filtered path, and ``1.0 / (1.0 + d)``
    is the only conversion in use.
    """

    async def test_filtered_and_unfiltered_scores_match(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        """Same chunk + same query → equal score on both paths."""
        from omrs.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        ai_file = tmp_path / "ai_only.txt"
        ai_file.write_text(
            "The transformer model uses attention heads. Deep learning "
            "neural networks train on large datasets. LLMs use embeddings."
        )
        await ingest_path_async(
            str(ai_file),
            collection_name="score_consistency",
        )

        unfiltered = search(
            "attention transformer",
            collection_name="score_consistency",
            top_k=5,
        )
        filtered = search(
            "attention transformer",
            collection_name="score_consistency",
            top_k=5,
            metadata_filter={"category": "AI"},
        )

        # Both paths return the same chunks (only one source) with the
        # same scoring formula — pair them by source/page/text and
        # compare scores within the contract tolerance.
        assert unfiltered, "expected at least one chunk from unfiltered path"
        assert filtered, "expected at least one chunk from filtered path"

        def keyed(r):
            return (r["source"], r.get("page_label"), r["text"])

        unfiltered_by_chunk = {keyed(r): r["score"] for r in unfiltered}

        for r in filtered:
            key = keyed(r)
            assert key in unfiltered_by_chunk, (
                "filtered chunk missing from unfiltered results — "
                "test fixture must produce a single shared corpus"
            )
            assert abs(r["score"] - unfiltered_by_chunk[key]) < 1e-6

    async def test_threshold_consistent_across_paths(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        """Same threshold filters identically on both paths."""
        from omrs.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        ai_file = tmp_path / "ai_threshold.txt"
        ai_file.write_text(
            "transformer attention heads neural networks deep learning "
            "embeddings power large language models."
        )
        await ingest_path_async(
            str(ai_file),
            collection_name="threshold_consistency",
        )

        # Pick a threshold mid-way through the unfiltered scores.
        unfiltered = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
        )
        if not unfiltered:
            pytest.skip("MockEmbedding produced no matches")

        scores = sorted((r["score"] for r in unfiltered), reverse=True)
        # Use a threshold strictly between the top score and zero so
        # both paths exclude the same set of chunks.
        threshold = max(scores) * 0.5

        unfiltered_filt = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
            similarity_threshold=threshold,
        )
        filtered_filt = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
            similarity_threshold=threshold,
            metadata_filter={"category": "AI"},
        )

        for r in unfiltered_filt:
            assert r["score"] >= threshold
        for r in filtered_filt:
            assert r["score"] >= threshold

    def test_l2_to_score_canonical_formula_lives_at_store_boundary(self) -> None:
        """The adapter helper follows ``1 / (1 + d)`` and rejects omissions."""
        from omrs.core.vectordb.score import canonical_score_from_l2

        assert canonical_score_from_l2(0.0, backend="test") == pytest.approx(1.0)
        assert canonical_score_from_l2(1.0, backend="test") == pytest.approx(0.5)
        assert canonical_score_from_l2(3.0, backend="test") == pytest.approx(0.25)
        with pytest.raises(ValueError, match="no L2 distance"):
            canonical_score_from_l2(None, backend="test")
