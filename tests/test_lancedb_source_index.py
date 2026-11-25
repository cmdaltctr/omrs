"""Per-file source reads use a scalar index, so their cost does not grow with the table.

Experiment 35, 2026-11-25: after the bounded compaction fix, each one-file
commit still read every row of the table three times: change detection
(``file_path`` and ``source_id`` counts), the durability count and the
stale-row scan (both on ``source_id``). On the test pod (4,096-dim vectors,
196,000 rows) this cost about 40 ms per file at 49,000 files. A BTREE index
on ``metadata.source_id`` and ``metadata.file_path`` turns each read into an
index lookup plus a scan of the rows written since the last compaction, which
also refreshes the index.
These tests pin the index, its refresh bound, and that every read and
search gives the same answer with and without it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.test_lancedb_compaction import _COLLECTION, _DIM, _IDENTITY, _commit_file

from omrs.core.ingestion.source_state import (
    assert_source_lineage_compatible,
    is_complete_current_version,
)
from omrs.core.vectordb.lancedb import compact
from omrs.core.vectordb.lancedb.filter import translate_where
from omrs.core.vectordb.lancedb.fts import fts_index_stats
from omrs.core.vectordb.lancedb.meta import metadata_field_names
from omrs.core.vectordb.lancedb.store import LanceVectorStore

_INDEXED = ("source_id", "file_path")


def _store(path: Path) -> LanceVectorStore:
    return LanceVectorStore(uri=str(path), embedding_identity=_IDENTITY)


def _plan(store: LanceVectorStore, where: dict) -> str:
    table = store._open_table(_COLLECTION)
    sql = translate_where(
        where, metadata_column="metadata", known_fields=metadata_field_names(table)
    )
    return table.to_lance().scanner(columns=["id"], filter=sql).explain_plan(True)


def _unindexed(store: LanceVectorStore) -> dict[str, int]:
    """Field name to the rows its index does not yet cover."""
    table = store._open_table(_COLLECTION)
    return {
        index.columns[0].removeprefix("metadata."): table.index_stats(index.name).num_unindexed_rows
        for index in table.list_indices()
        if index.index_type == "BTree"
    }


@pytest.fixture
def small(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compact at 8 small fragments; 16 rows fill a fragment."""
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    monkeypatch.setattr(compact, "COMPACTION_TARGET_ROWS", 16)


def test_source_reads_use_a_scalar_index_with_bounded_unindexed_rows(
    tmp_path: Path, small: None
) -> None:
    """Both source fields get an index, and the rows it misses stay bounded."""
    store = _store(tmp_path / "lancedb")
    worst = 0
    for number in range(120):
        _commit_file(store, number)
        if number >= 10:
            unindexed = _unindexed(store)
            assert set(unindexed) == set(_INDEXED), f"after file {number}"
            worst = max(worst, *unindexed.values())
    # Bound: each compaction refreshes the index, so at most the rows written
    # since the last one (under eight two-row files) are unindexed.
    assert worst < 2 * 8
    assert "ScalarIndexQuery" in _plan(store, {"source_id": "source-5"})
    assert "ScalarIndexQuery" in _plan(store, {"file_path": "/corpus/file_005.md"})
    assert store.count(_COLLECTION) == 240


def _source_answers(store: LanceVectorStore) -> list:
    """Every per-file source read, for sources old (indexed) and new (unindexed)."""
    answers = []
    for number in (0, 3, 57, 118, 119, 999):
        path, source_id = f"/corpus/file_{number:03d}.md", f"source-{number}"
        assert_source_lineage_compatible(store, _COLLECTION, file_path=path, source_id=source_id)
        answers.append(
            is_complete_current_version(
                store,
                _COLLECTION,
                source_id=source_id,
                content_hash=f"passage-{number}",
                index_identity="idx",
                source_version=f"passage-{number}",
            )
        )
        answers.append(store.count_where(_COLLECTION, {"file_path": path}))
        answers.append(
            sorted(
                (text, meta["source_chunk_index"])
                for _id, text, meta in store.iter_filtered_documents(
                    _COLLECTION, {"source_id": source_id}
                )
            )
        )
    return answers


def _filter_answers(store: LanceVectorStore) -> list:
    """Counts and dense results for each filter shape on the indexed fields."""
    wheres = [
        {"source_id": "source-7"},
        {"source_id": {"$ne": "source-7"}},
        {"source_id": {"$in": ["source-1", "source-90", "source-119"]}},
        {"source_id": {"$nin": ["source-1", "source-90"]}},
        {"file_path": {"$in": ["/corpus/file_002.md", "/corpus/file_118.md"]}},
        {"$or": [{"file_path": "/corpus/file_004.md"}, {"source_id": "source-80"}]},
        {"$and": [{"source_id": "source-3"}, {"source_chunk_index": 1}]},
    ]
    query = [0.5] + [0.1] * (_DIM - 1)
    answers = []
    for where in wheres:
        answers.append(store.count_where(_COLLECTION, where))
        answers.append(
            [
                (row["document"], row["score"])
                for row in store.query_dense(_COLLECTION, query, 300, where=where)
            ]
        )
    return answers


def test_reads_and_searches_match_a_store_without_the_index(
    tmp_path: Path, small: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index changes cost only: every answer equals the unindexed twin's."""
    indexed = _store(tmp_path / "a")
    for number in range(120):
        _commit_file(indexed, number)
    monkeypatch.setattr(compact, "SOURCE_INDEX_FIELDS", (), raising=False)
    plain = _store(tmp_path / "b")
    for number in range(120):
        _commit_file(plain, number)

    assert set(_unindexed(indexed)) == set(_INDEXED)
    assert _unindexed(plain) == {}
    assert _source_answers(indexed) == _source_answers(plain)
    assert _filter_answers(indexed) == _filter_answers(plain)


def test_replacement_finds_stale_rows_in_indexed_and_new_fragments(
    tmp_path: Path, small: None
) -> None:
    """A changed source is replaced whether its old rows are indexed or not yet."""
    store = _store(tmp_path / "lancedb")
    for number in range(120):
        _commit_file(store, number)
    # Source 2 is long indexed; source 119 was written last and is not.
    for number in (2, 119):
        _commit_file(store, number, text="changed")

    assert store.count(_COLLECTION) == 240
    for number in (2, 119):
        rows = list(store.iter_filtered_documents(_COLLECTION, {"source_id": f"source-{number}"}))
        assert sorted(text for _id, text, _meta in rows) == [
            f"changed {number} chunk 0",
            f"changed {number} chunk 1",
        ]


def test_the_stale_row_scan_reads_no_vectors_text_or_whole_metadata(
    tmp_path: Path, small: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scan needs only each row's ID and attempt, so its cost is the same for any vector width.

    With an index, Lance reads every requested column of the rows not yet in
    it. A changed file near the end of the table is the case that pays.
    """
    from lance.dataset import LanceDataset

    store = _store(tmp_path / "lancedb")
    for number in range(30):
        _commit_file(store, number)
    scans: list[list[str]] = []
    original = LanceDataset.scanner

    def _spy(self, *args, **kwargs):
        if kwargs.get("filter"):
            scans.append(list(kwargs.get("columns") or ["<all columns>"]))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(LanceDataset, "scanner", _spy)
    _commit_file(store, 29, text="changed")

    assert scans, "the changed file must run the stale-row scan"
    wide = {"vector", "text", "metadata", "<all columns>"}
    assert all(not wide & set(columns) for columns in scans), scans
    assert store.count(_COLLECTION) == 60


def test_an_existing_store_without_the_index_gains_it_and_keeps_working(
    tmp_path: Path, small: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store built before the index opens, reads right, then gets the index on a later write."""
    store = _store(tmp_path / "lancedb")
    monkeypatch.setattr(compact, "SOURCE_INDEX_FIELDS", (), raising=False)
    for number in range(60):
        _commit_file(store, number)
    assert _unindexed(store) == {}
    before = _source_answers(store)

    monkeypatch.undo()
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    monkeypatch.setattr(compact, "COMPACTION_TARGET_ROWS", 16)
    reopened = _store(tmp_path / "lancedb")
    assert _source_answers(reopened) == before
    for number in range(60, 80):
        _commit_file(reopened, number)
    assert set(_unindexed(reopened)) == set(_INDEXED)
    assert reopened.count(_COLLECTION) == 160


def test_a_schema_rebuild_drops_the_index_and_a_later_write_restores_it(
    tmp_path: Path, small: None
) -> None:
    """A new metadata key rewrites the table without indexes; the next compaction adds them."""
    store = _store(tmp_path / "lancedb")
    for number in range(40):
        _commit_file(store, number)
    store.upsert_precomputed(
        _COLLECTION,
        ["extra-row"],
        ["extra"],
        [{"file_path": "/corpus/extra.md", "source_id": "extra", "brand_new_key": "x"}],
        [[1.0] + [0.0] * (_DIM - 1)],
        embedding_identity=_IDENTITY,
    )
    assert _unindexed(store) == {}
    for number in range(40, 60):
        _commit_file(store, number)
    assert set(_unindexed(store)) == set(_INDEXED)
    assert store.count_where(_COLLECTION, {"source_id": "extra"}) == 1
    assert store.count(_COLLECTION) == 121


def test_index_upkeep_leaves_the_full_text_index_alone(tmp_path: Path, small: None) -> None:
    """Only the source indexes are refreshed; full-text upkeep stays with its own code."""
    store = _store(tmp_path / "lancedb")
    for number in range(4):
        _commit_file(store, number)
    store.prepare_native_sparse(_COLLECTION)
    for number in range(4, 60):
        _commit_file(store, number)
    indexed, unindexed = fts_index_stats(store._open_table(_COLLECTION))
    assert (indexed, unindexed) == (8, 112)


def test_a_new_source_skips_the_stale_row_scan_and_a_changed_one_runs_it(
    tmp_path: Path, small: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stale-row scan runs only when the source holds rows of an older attempt.

    On LanceDB the scan reads every column of the unindexed rows, so on the
    first ingest of a file a count of the source's rows replaces it.
    """
    store = _store(tmp_path / "lancedb")
    for number in range(20):
        _commit_file(store, number)
    scans: list[dict] = []
    original = store.iter_filtered_fields

    def _spy(collection_name, where, fields, page_size=None):
        scans.append(where)
        return original(collection_name, where, fields, page_size)

    monkeypatch.setattr(store, "iter_filtered_fields", _spy)
    _commit_file(store, 20)
    assert scans == []
    _commit_file(store, 4, text="changed")
    assert scans == [{"source_id": "source-4"}]
    assert store.count(_COLLECTION) == 42
    assert store.count_where(_COLLECTION, {"source_id": "source-4"}) == 2
