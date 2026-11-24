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

from pathlib import Path

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


def _commit_file(store: LanceVectorStore, number: int, *, text: str = "passage") -> None:
    """Commit one two-chunk source through the production commit seam."""
    path = f"/corpus/file_{number:03d}.md"
    nodes = []
    for chunk in range(2):
        node = TextNode(text=f"{text} {number} chunk {chunk}", metadata={"file_path": path})
        node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=path)
        vector = [0.0] * _DIM
        vector[(number + chunk) % _DIM] = 1.0
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
