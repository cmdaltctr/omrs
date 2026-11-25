"""LanceDB tables written one source at a time keep a bounded fragment count.

Experiment 35 (test pod, FreshStack, one ``Engine.ingest`` per file): the
store step grew to about 2 s per file after 3,300 files. Each append adds
one fragment, and the durability count and the stale-row scan of every
commit visit all fragments. A local benchmark gave 63 ms for the count and
108 ms for the scan at 3,000 fragments, and 0.5 ms and 1.2 ms after one
compaction. These tests pin the bound and show that compaction leaves the
stored rows, their order, the table metadata and the search scores unchanged.
"""

from __future__ import annotations

import importlib
import math
import random
from pathlib import Path

import lancedb
import pyarrow as pa
import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from omrs.core.ingestion.commit import PreparedSource, commit_prepared_source
from omrs.core.ingestion.source_state import new_source_attempt, stamp_source_lineage
from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb import compact
from omrs.core.vectordb.lancedb.meta import OMRS_EPOCH_KEY, read_dataset_epoch
from omrs.core.vectordb.lancedb.store import LanceVectorStore

_DIM = 8
_IDENTITY = EmbeddingIdentity(provider="test", model="mock", index_identity="idx")
_COLLECTION = "docs"


def _fragments(store: LanceVectorStore) -> int:
    return len(store._open_table(_COLLECTION).to_lance().get_fragments())


def _commit_file(
    store: LanceVectorStore, number: int, *, text: str = "passage", distinct: bool = False
) -> None:
    """Commit one two-chunk source through the production commit seam.

    *distinct* gives each chunk its own unit vector, so search scores have no ties.
    """
    path = f"/corpus/file_{number:03d}.md"
    nodes = []
    for chunk in range(2):
        node = TextNode(text=f"{text} {number} chunk {chunk}", metadata={"file_path": path})
        node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=path)
        vector = [0.0] * _DIM
        vector[(number + chunk) % _DIM] = 1.0
        if distinct:
            rng = random.Random(number * 2 + chunk)  # noqa: S311
            raw = [rng.gauss(0.0, 1.0) for _ in range(_DIM)]
            norm = math.sqrt(sum(x * x for x in raw))
            vector = [x / norm for x in raw]
        node.embedding = vector
        nodes.append(node)
    attempt = new_source_attempt()
    source_id = f"source-{number}"
    stamp_source_lineage(
        nodes,
        file_path=path,
        source_id=source_id,
        content_hash=f"{text}-{number}",
        index_identity="idx",
        source_version=f"{text}-{number}",
        source_attempt=attempt,
    )
    prepared = PreparedSource(path, source_id, attempt, len(nodes), 0.0, None)
    commit_prepared_source(
        nodes,
        prepared,
        collection_name=_COLLECTION,
        store=store,
        embed_model=MockEmbedding(embed_dim=_DIM),
    )


def _rows(store: LanceVectorStore) -> list[tuple[str, str]]:
    return [(text, meta["file_path"]) for _id, text, meta in store.iter_documents(_COLLECTION)]


def _ranked(store: LanceVectorStore, query: list[float]) -> list[tuple[str, float]]:
    return [(row["document"], row["score"]) for row in store.query_dense(_COLLECTION, query, 40)]


@pytest.fixture
def small_threshold(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    return 8


def test_single_file_commits_keep_fragment_count_bounded(
    tmp_path: Path, small_threshold: int
) -> None:
    """Forty one-file commits leave fewer fragments than the threshold.

    The per-file store cost follows the fragment count, so a bounded
    count keeps the per-file cost flat as the table grows.
    """
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    for number in range(40):
        _commit_file(store, number)
        assert _fragments(store) < small_threshold, f"after file {number}"
    assert store.count(_COLLECTION) == 80


def test_compaction_keeps_rows_order_metadata_and_scores(
    tmp_path: Path, small_threshold: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compacted table and an uncompacted twin return the same data."""
    compacted = LanceVectorStore(uri=str(tmp_path / "a"), embedding_identity=_IDENTITY)
    for number in range(20):
        _commit_file(compacted, number)
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 10**9)
    plain = LanceVectorStore(uri=str(tmp_path / "b"), embedding_identity=_IDENTITY)
    for number in range(20):
        _commit_file(plain, number)

    assert _fragments(compacted) < small_threshold <= _fragments(plain)
    # Row IDs carry the random attempt ID, so compare text and source in order.
    assert _rows(compacted) == _rows(plain)
    query = [0.5] + [0.1] * (_DIM - 1)
    assert _ranked(compacted, query) == _ranked(plain, query)
    # Each table mints its own random epoch; every other entry must match.
    meta_a = compacted.get_collection_metadata(_COLLECTION)
    meta_b = plain.get_collection_metadata(_COLLECTION)
    assert meta_a.pop(OMRS_EPOCH_KEY) and meta_b.pop(OMRS_EPOCH_KEY)
    assert meta_a == meta_b


def test_compaction_keeps_dataset_epoch(tmp_path: Path, small_threshold: int) -> None:
    """Compaction is a row-preserving rewrite, not a new dataset incarnation."""
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    _commit_file(store, 0)
    epoch = read_dataset_epoch(store._open_table(_COLLECTION))
    for number in range(1, 20):
        _commit_file(store, number)
    assert _fragments(store) < small_threshold
    assert read_dataset_epoch(store._open_table(_COLLECTION)) == epoch


def test_replacement_after_compaction_removes_stale_rows(
    tmp_path: Path, small_threshold: int
) -> None:
    """Re-ingesting a source whose rows were compacted still replaces them."""
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    for number in range(20):
        _commit_file(store, number)
    _commit_file(store, 3, text="changed")

    assert store.count(_COLLECTION) == 40
    texts = [
        text
        for _id, text, meta in store.iter_documents(_COLLECTION)
        if meta["file_path"].endswith("file_003.md")
    ]
    assert sorted(texts) == ["changed 3 chunk 0", "changed 3 chunk 1"]


def test_a_failed_compaction_leaves_the_finished_replacement_in_place(
    tmp_path: Path,
    small_threshold: int,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Compaction only tidies rows already written, so its failure must not fail the write.

    A raise from compaction once skipped the stale-row cleanup and left the old and
    the new attempt of the source side by side.
    """
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    for number in range(small_threshold - 1):
        _commit_file(store, number)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    optimizer = importlib.import_module("lance.dataset").DatasetOptimizer
    monkeypatch.setattr(optimizer, "compact_files", fail)
    _commit_file(store, 3, text="changed")  # the eighth small fragment starts a compaction

    texts = sorted(t for t, path in _rows(store) if path.endswith("file_003.md"))
    assert texts == ["changed 3 chunk 0", "changed 3 chunk 1"]
    assert store.count(_COLLECTION) == 2 * (small_threshold - 1)
    assert "disk full" in caplog.text


def test_native_fts_index_survives_compaction(
    tmp_path: Path, small_threshold: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compaction remaps an existing full-text index; rankings stay equal."""
    twins = []
    for name, threshold in (("a", small_threshold), ("b", 10**9)):
        monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", threshold)
        store = LanceVectorStore(uri=str(tmp_path / name), embedding_identity=_IDENTITY)
        for number in range(4):
            _commit_file(store, number)
        store.prepare_native_sparse(_COLLECTION)
        for number in range(4, 20):
            _commit_file(store, number)
        twins.append(store)
    compacted, plain = twins

    assert _fragments(compacted) < small_threshold <= _fragments(plain)
    ranked = [
        [(row["document"], row["score"]) for row in s.query_native_sparse(_COLLECTION, "7", 40)]
        for s in twins
    ]
    assert ranked[0] and ranked[0] == ranked[1]


# Experiment 35 pod, 2026-11-25: the store step still grew after the fix above.
# Lance counts every fragment under 1,048,576 rows as small, so each compaction
# merged the big fragment too and rewrote the whole table: 1 s per compaction
# at 8,000 rows, 12.4 s at 196,000 rows. A full fragment must stay as it is.

_TARGET = 16  # rows; eight two-row files fill one fragment


def _table_rows(store: LanceVectorStore) -> list[dict]:
    """Every column of every row, in table order: IDs, text, vectors and metadata."""
    return store._open_table(_COLLECTION).to_arrow().to_pylist()


def _fragment_ids(store: LanceVectorStore) -> dict[int, int]:
    """Fragment ID to row count."""
    dataset = store._open_table(_COLLECTION).to_lance()
    return {f.fragment_id: f.physical_rows for f in dataset.get_fragments()}


def _results(store: LanceVectorStore) -> list[list[tuple]]:
    """Dense and full-text results for a fixed query set."""
    dense = []
    for seed in range(5):
        rng = random.Random(1000 + seed)  # noqa: S311
        query = [rng.gauss(0.0, 1.0) for _ in range(_DIM)]
        dense.append(
            [
                (row["id"], row["document"], row["score"])
                for row in store.query_dense(_COLLECTION, query, 25)
            ]
        )
    # Full-text scores tie often here; any compaction, bounded or whole-table,
    # may reorder rows with equal scores, so compare each full result list sorted.
    sparse = [
        sorted(
            (row["score"], row["id"], row["document"])
            for row in store.query_native_sparse(_COLLECTION, term, 200)
        )
        for term in ("7", "chunk", "passage 3")
    ]
    return dense + sparse


@pytest.fixture
def bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Threshold 8 small fragments; a fragment of 16 rows is full."""
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    # raising=False: before the fix the module had no target to patch.
    monkeypatch.setattr(compact, "COMPACTION_TARGET_ROWS", _TARGET, raising=False)


def test_compaction_leaves_full_fragments_and_results_alone(
    tmp_path: Path, bounded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A later compaction rewrites only the small fragments; data and results stay the same."""
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 10**9)
    for number in range(4):
        _commit_file(store, number, distinct=True)
    store.prepare_native_sparse(_COLLECTION)
    for number in range(4, 40):
        _commit_file(store, number, distinct=True)
    rows, results = _table_rows(store), _results(store)

    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    assert compact.compact_if_fragmented(store._open_table(_COLLECTION))
    full = {fid: rows for fid, rows in _fragment_ids(store).items() if rows == _TARGET}
    assert len(full) >= 3 and max(_fragment_ids(store).values()) <= _TARGET
    assert _table_rows(store) == rows
    assert _results(store) == results

    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 10**9)
    for number in range(40, 52):
        _commit_file(store, number, distinct=True)
    rows, results = _table_rows(store), _results(store)
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    assert compact.compact_if_fragmented(store._open_table(_COLLECTION))

    after = _fragment_ids(store)
    assert {fid: after.get(fid) for fid in full} == full, "a full fragment was rewritten"
    assert max(after.values()) <= _TARGET
    assert _table_rows(store) == rows
    assert _results(store) == results


def test_full_fragments_do_not_trigger_compaction(tmp_path: Path, bounded: None) -> None:
    """Only small fragments count towards the threshold, so no empty compaction runs."""
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=_IDENTITY)
    for number in range(80):
        _commit_file(store, number)
    sizes = _fragment_ids(store)
    assert sum(1 for rows in sizes.values() if rows >= _TARGET) >= 8
    assert sum(1 for rows in sizes.values() if rows < _TARGET) < 8

    table = store._open_table(_COLLECTION)
    version = table.version
    assert not compact.compact_if_fragmented(table)
    assert store._open_table(_COLLECTION).version == version


# Commit 784e478c made compaction count and merge only small fragments. Deleted rows
# inside a full fragment then never raised the count (CodeRabbit, PR 224). Lance
# rewrites a fragment once more than 10% of its rows are deleted
# (materialize_deletions_threshold; exactly 10% stays, the threshold is a 32-bit float),
# so such a fragment now counts as a candidate too.

_FULL = 20  # rows in a full fragment of these tests; 2 deleted rows is exactly 10%


def _fragmented_table(tmp_path: Path, deleted_each: int):
    """Eight full fragments of 20 rows, each with *deleted_each* rows deleted."""
    table = lancedb.connect(str(tmp_path)).create_table(
        "plain", data=pa.table({"id": [0], "vector": [[0.0] * _DIM]})
    )
    table.delete("id = 0")
    for part in range(8):
        ids = list(range(part * _FULL, (part + 1) * _FULL))
        table.add(pa.table({"id": ids, "vector": [[float(i)] * _DIM for i in ids]}))
    if deleted_each:
        for part in range(8):
            first = part * _FULL
            table.delete(f"id >= {first} AND id < {first + deleted_each}")
    return table


def _deleted_rows(table) -> int:
    return sum(f.num_deletions for f in table.to_lance().get_fragments())


@pytest.mark.parametrize(
    ("deleted_each", "compacts"), [(0, False), (1, False), (2, False), (3, True)]
)
def test_a_full_fragment_counts_once_over_10_percent_of_its_rows_are_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deleted_each: int, compacts: bool
) -> None:
    """Eight full fragments reach the threshold of 8 only with more than 10% deleted rows."""
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", 8)
    monkeypatch.setattr(compact, "COMPACTION_TARGET_ROWS", _FULL)
    table = _fragmented_table(tmp_path, deleted_each)
    live = sorted(row["id"] for row in table.to_arrow().to_pylist())
    version = table.version
    assert _deleted_rows(table) == 8 * deleted_each

    assert compact.compact_if_fragmented(table) is compacts

    after = lancedb.connect(str(tmp_path)).open_table("plain")
    assert sorted(row["id"] for row in after.to_arrow().to_pylist()) == live
    if compacts:
        assert _deleted_rows(after) == 0, "the deleted rows were not removed"
    else:
        assert after.version == version and _deleted_rows(after) == 8 * deleted_each
