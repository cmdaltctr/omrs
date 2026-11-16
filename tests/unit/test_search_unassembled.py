"""The unassembled search option returns ranked stored chunks (design D39, R-1).

With ``unassembled=True`` a search skips only the context-assembly stage:
each row is one stored chunk, in final rank order. The default keeps the
assembled rows unchanged.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from omrs.core.settings import EffectiveSettings, MetadataBlock
from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb.store import LanceVectorStore

_IDENTITY = EmbeddingIdentity(provider="test", model="fixed")
_QUERY = [1.0, 0.0, 0.0, 0.0]


class _FixedQueryEmbedding:
    """Query embedder that always returns the same unit vector."""

    model_name = "fixed"

    def get_query_embedding(self, _query: str) -> list[float]:
        return list(_QUERY)


def _unit(angle: float) -> list[float]:
    """Return a unit vector at *angle* radians from the query vector."""
    return [math.cos(angle), math.sin(angle), 0.0, 0.0]


def _row(source: str, index: int, text: str, angle: float, page: str) -> dict[str, Any]:
    return {
        "id": f"{source}-{index}",
        "text": text,
        "embedding": _unit(angle),
        "metadata": {
            "file_path": f"/docs/{source}.pdf",
            "page_label": page,
            "source_id": source,
            "source_version": "v1",
            "chunk_id": f"{source}-{index}",
            "source_chunk_index": index,
            "source_chunk_count": 50,
        },
    }


def _write(store: LanceVectorStore, collection: str, rows: list[dict[str, Any]]) -> None:
    store.upsert_precomputed(
        collection,
        [row["id"] for row in rows],
        [row["text"] for row in rows],
        [row["metadata"] for row in rows],
        [row["embedding"] for row in rows],
        embedding_identity=_IDENTITY,
    )


def _interleaved_rows() -> list[dict[str, Any]]:
    """Chunk 5 at rank 1, another source at rank 2, chunk 6 at rank 3."""
    return [
        _row("alpha", 5, "red green blue shared overlap words", 0.0, "5"),
        _row("beta", 0, "an unrelated passage from another file", 0.1, "1"),
        _row("alpha", 6, "shared overlap words then yellow purple", 0.2, "6"),
        _row("alpha", 20, "far away chunk of the first file", 1.2, "20"),
    ]


def _many_rows(count: int) -> list[dict[str, Any]]:
    # Consecutive indexes of one source, so assembly would merge neighbours.
    return [
        _row("bulk", index, f"stored chunk number {index} text", 0.01 * index, str(index))
        for index in range(count)
    ]


def _engine(tmp_path: Path, rows: list[dict[str, Any]]):
    from omrs.engine import Engine

    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    _write(store, "docs", rows)
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    return Engine(settings, store=store, embed_model=_FixedQueryEmbedding())


def _search(engine, **kwargs: Any) -> list[dict]:
    return engine.search("query", collection_name="docs", rerank=False, hybrid=False, **kwargs)


def test_unassembled_returns_exactly_top_k_stored_chunks(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _many_rows(120))

    rows = _search(engine, top_k=100, fetch_k=100, unassembled=True)

    assert len(rows) == 100
    assert [row["chunk_id"] for row in rows] == [f"bulk-{i}" for i in range(100)]
    scores = [row["score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    for index, row in enumerate(rows):
        assert row["text"] == f"stored chunk number {index} text"
        assert row["page_label"] == str(index)
        assert "chunk_ids" not in row and "page_labels" not in row
    engine.close()


def test_unassembled_with_fewer_chunks_returns_every_chunk(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _many_rows(40))

    rows = _search(engine, top_k=100, fetch_k=100, unassembled=True)

    assert [row["chunk_id"] for row in rows] == [f"bulk-{i}" for i in range(40)]
    assert all("chunk_ids" not in row for row in rows)
    engine.close()


def test_interleaved_ranking_stays_three_rows_in_rank_order(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _interleaved_rows())

    rows = _search(engine, top_k=3, unassembled=True)

    assert [row["chunk_id"] for row in rows] == ["alpha-5", "beta-0", "alpha-6"]
    assert [row["page_label"] for row in rows] == ["5", "1", "6"]
    assert rows[0]["text"] == "red green blue shared overlap words"
    assert rows[2]["text"] == "shared overlap words then yellow purple"
    assert all("chunk_ids" not in row and "page_labels" not in row for row in rows)
    engine.close()


def test_default_still_merges_adjacent_chunks(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _interleaved_rows())

    rows = _search(engine, top_k=3)

    assert [row["chunk_id"] for row in rows] == ["alpha-5", "beta-0"]
    assert rows[0]["chunk_ids"] == ["alpha-5", "alpha-6"]
    assert rows[0]["page_labels"] == ["5", "6"]
    assert rows[0]["text"] == "red green blue shared overlap words then yellow purple"
    engine.close()


def test_unassembled_with_expansion_refuses_before_the_query(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _interleaved_rows())

    with (
        patch.object(engine.store, "query_dense") as query_dense,
        pytest.raises(ValueError, match="unassembled") as refusal,
    ):
        _search(engine, top_k=3, unassembled=True, expand_window=1)

    assert "expand_window" in str(refusal.value)
    query_dense.assert_not_called()
    engine.close()


def test_engine_search_passes_the_option_to_core_search(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _interleaved_rows())
    captured: dict[str, Any] = {}

    def _fake_search(_query: str, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    with patch("omrs.core.retrieval.pipeline.search", side_effect=_fake_search):
        engine.search("query", collection_name="docs", unassembled=True)

    assert captured["unassembled"] is True
    engine.close()


def test_user_profile_collection_refuses_the_option(tmp_path: Path, monkeypatch) -> None:
    import omrs.engine_profiles as engine_profiles

    engine = _engine(tmp_path, _interleaved_rows())
    binding = SimpleNamespace(user=True, name="my-profile")
    monkeypatch.setattr(
        engine, "_resolve_bound", lambda _collection: (engine._effective_settings, binding)
    )

    def _no_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the profile graph must not run")

    monkeypatch.setattr(engine_profiles, "_run", _no_run)
    with pytest.raises(ValueError, match="unassembled") as refusal:
        engine.search("query", collection_name="docs", unassembled=True)

    assert "my-profile" in str(refusal.value)
    engine.close()
