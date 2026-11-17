"""A native full-text query never writes to the store (design D26).

The LanceDB FTS query scans unindexed rows and honours delete tombstones
at query time, so the read path needs no index creation and no
``optimize()``. These tests pin that a query leaves the table version
and the FTS row counts unchanged, and that a collection with no index
falls back to BM25 with a warning that names the ingest remedy.
"""

from __future__ import annotations

import logging
import threading

import pytest

from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb.fts import ensure_fts_index, fts_index_stats

_IDENTITY = EmbeddingIdentity(provider="test", model="mock")
_CORPUS = [
    ("history-1", "the colosseum of ancient rome", "history"),
    ("science-1", "quantum computing with qubits", "science"),
    ("sport-1", "modern stadium concrete design", "sport"),
]


def _lance_store(tmp_path):
    from omrs.core.vectordb.lancedb.store import LanceVectorStore

    return LanceVectorStore(uri=str(tmp_path / "fts"))


def _write_rows(store, collection: str, rows: list[tuple[str, str, str]]) -> None:
    store.upsert_precomputed(
        collection,
        [row_id for row_id, _text, _category in rows],
        [text for _row_id, text, _category in rows],
        [{"category": category} for _row_id, _text, category in rows],
        [[0.5, 0.5, 0.5, 0.5]] * len(rows),
        embedding_identity=_IDENTITY,
    )


def _indexed_store_with_late_row(tmp_path):
    """Return a store whose FTS index has one unindexed row."""
    store = _lance_store(tmp_path)
    _write_rows(store, "docs", _CORPUS)
    ensure_fts_index(store._open_table("docs"))
    _write_rows(store, "docs", [("late-1", "zephyr late token", "science")])
    return store


def test_query_leaves_version_and_fts_counts_unchanged(tmp_path) -> None:
    store = _indexed_store_with_late_row(tmp_path)
    table = store._open_table("docs")
    version_before = table.version
    stats_before = fts_index_stats(table)
    assert stats_before is not None and stats_before[1] == 1

    rows = store.query_native_sparse("docs", "zephyr", 5)

    after = store._open_table("docs")
    assert after.version == version_before
    assert fts_index_stats(after) == stats_before
    # The unindexed row is still served: the engine scans it at query time.
    assert [row["id"] for row in rows] == ["late-1"]


def test_row_deleted_after_index_is_not_returned(tmp_path) -> None:
    store = _lance_store(tmp_path)
    _write_rows(store, "docs", _CORPUS)
    ensure_fts_index(store._open_table("docs"))
    store.delete_where("docs", {"category": "history"})
    version_before = store._open_table("docs").version

    assert store.query_native_sparse("docs", "colosseum", 5) == []
    assert store._open_table("docs").version == version_before


def test_query_without_index_creates_no_index(tmp_path) -> None:
    store = _lance_store(tmp_path)
    _write_rows(store, "docs", _CORPUS)
    version_before = store._open_table("docs").version

    with pytest.raises(ValueError, match="Ingest the collection again"):
        store.query_native_sparse("docs", "colosseum", 5)

    assert store.native_sparse_coverage("docs") is None
    assert store._open_table("docs").version == version_before


def test_hybrid_without_index_warns_with_ingest_remedy_and_serves_bm25(
    tmp_path, monkeypatch, caplog, effective_settings
) -> None:
    import omrs.core.retrieval.dense as dense
    import omrs.core.retrieval.pipeline as retrieval
    from omrs.core.retrieval.sparse_dispatch import reset_warning_state

    store = _lance_store(tmp_path)
    _write_rows(store, "docs", _CORPUS)
    monkeypatch.setattr(dense, "_embed_query", lambda _q, _em=None, _c=None: [0.5] * 4)
    reset_warning_state()
    settings = effective_settings(
        hybrid_enabled=True,
        hybrid_sparse_backend="native",
        rerank_enabled=False,
        similarity_threshold=0.0,
    )
    with caplog.at_level(logging.WARNING):
        results = retrieval.search(
            "colosseum",
            top_k=2,
            rerank=False,
            hybrid=True,
            store=store,
            collection_name="docs",
            effective_settings=settings,
            include_diagnostics=True,
        )

    assert results[0]["id"] == "history-1"
    assert all(row.get("sparse_backend") == "bm25" for row in results)
    fallback = [r.message for r in caplog.records if "Falling back to the BM25" in r.message]
    assert len(fallback) == 1
    assert "ingest" in fallback[0].lower()
    assert store.native_sparse_coverage("docs") is None


class _PartialCoverageStore:
    def native_sparse_coverage(self, collection_name: str) -> dict:
        return {"indexed": 3, "unindexed": 1, "total": 4}


def test_mixed_coverage_warning_names_the_next_ingest(caplog) -> None:
    from omrs.core.retrieval.sparse_dispatch import (
        _emit_mixed_coverage_warning,
        reset_warning_state,
    )

    reset_warning_state()
    with caplog.at_level(logging.WARNING):
        _emit_mixed_coverage_warning("docs", _PartialCoverageStore())  # type: ignore[arg-type]

    (message,) = [r.getMessage() for r in caplog.records]
    assert "3/4" in message
    assert "next ingest" in message
    assert "next native query" not in message


def test_concurrent_queries_leave_version_unchanged(tmp_path) -> None:
    store = _indexed_store_with_late_row(tmp_path)
    version_before = store._open_table("docs").version
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _query() -> None:
        try:
            barrier.wait()
            store.query_native_sparse("docs", "zephyr", 5)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=_query) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store._open_table("docs").version == version_before
