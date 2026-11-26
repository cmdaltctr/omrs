"""Experiment 35 ingest stage keeps the LanceDB version count bounded.

Rule under test (pre-freeze amendment 2026-11-24, protocol section 7): every
``stages35.VERSION_CLEANUP_EVERY`` ingested files the stage deletes every
table version but the latest. Each one-file write adds a version, and each
table open lists them all, so without the cleanup the per-file store cost
grows with the number of files already written. The cleanup keeps the rows,
their order and ``table.version``, so a sealed index and its G2 rebuild give
the same search results and the same fingerprint version.

The stub engine writes each file through the real OMRS commit seam into the
index's own store. No model and no network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import lancedb
import pytest
from experiments._lib.trace import TraceWriter
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from tests._exp35_fixtures import load

from omrs.core.ingestion.commit import PreparedSource, commit_prepared_source
from omrs.core.ingestion.source_state import new_source_attempt, stamp_source_lineage
from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb import compact
from omrs.core.vectordb.lancedb.store import LanceVectorStore

outputs35 = load("outputs35")
stages35 = load("stages35")

INDEX = "e4b-c1024"
_DIM = 8
_FILES = 40
_EVERY = 8
_ENV = {
    "gpu": "NVIDIA GeForce RTX 4090",
    "image": "runpod/base@sha256:" + "1" * 64,
    "llama_cpp_build": 11941,
    "gguf_sha256": {"Qwen3-Embedding-4B-Q8_0.gguf": "a" * 64},
}


class _WritingEngine:
    """Stub engine: ``ingest`` commits two chunks of the file into a real LanceDB store."""

    def __init__(self, uri: Path) -> None:
        identity = EmbeddingIdentity(provider="test", model="mock", index_identity="idx")
        self.store = LanceVectorStore(uri=str(uri), embedding_identity=identity)

    async def ingest(self, path: str, *, collection_name: str) -> dict[str, Any]:
        name = Path(path).name
        number = int(name.split(".")[0])
        nodes = []
        for chunk in range(2):
            node = TextNode(text=f"passage {number} chunk {chunk}", metadata={"file_path": path})
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=path)
            vector = [0.0] * _DIM
            vector[(number + chunk) % _DIM] = 1.0
            node.embedding = vector
            nodes.append(node)
        attempt = new_source_attempt()
        stamp_source_lineage(
            nodes,
            file_path=path,
            source_id=name,
            content_hash=name,
            index_identity="idx",
            source_version=name,
            source_attempt=attempt,
        )
        commit_prepared_source(
            nodes,
            PreparedSource(path, name, attempt, 2, 0.0, None),
            collection_name=collection_name,
            store=self.store,
            embed_model=MockEmbedding(embed_dim=_DIM),
        )
        return {
            "status": "ok",
            "chunks_created": 2,
            "file_details": [{"file": name, "status": "indexed", "chunks": 2}],
        }


def _ctx(root: Path, files: list[Path]) -> Any:
    layout = outputs35.Layout(root / "out")
    folder = layout.index_dir("freshstack", INDEX)
    trace = TraceWriter(
        folder / "traces.jsonl",
        benchmark_revision="test",
        run_id=f"freshstack/{INDEX}/run1",
        arm=INDEX,
        repetition=1,
        effective_settings={"setup": INDEX},
        model_identities={},
    )
    return stages35.Ctx(
        dataset="freshstack",
        setup=INDEX,
        kind="index",
        run=1,
        questions=[],
        layout=layout,
        key=outputs35.run_key(None, None, 20261101, ["q1"], config={"harness_commit": "c"}),
        resume=False,
        trace=trace,
        engine=_WritingEngine(layout.store(INDEX)),
        settings=type("S", (), {"retrieval": type("R", (), {"hybrid_sparse_backend": "bm25"})})(),
        files=files,
        environment=dict(_ENV),
    )


def _files(root: Path) -> list[Path]:
    folder = root / "passages"
    folder.mkdir(parents=True)
    paths = [folder / f"{number:03d}.md" for number in range(_FILES)]
    for path in paths:
        path.write_text(path.name, encoding="utf-8")
    return paths


def _table(ctx: Any) -> Any:
    return lancedb.connect(str(ctx.layout.store(ctx.index))).open_table(ctx.collection)


def _build(root: Path) -> Any:
    ctx = _ctx(root, _files(root))
    assert asyncio.run(stages35.ingest_stage(ctx)) == 0
    return ctx


def _ranked(ctx: Any) -> list[tuple[str, float]]:
    query = [0.5] + [0.1] * (_DIM - 1)
    rows = ctx.engine.store.query_dense(ctx.collection, query, 2 * _FILES)
    return [(row["document"], row["score"]) for row in rows]


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compact, "FRAGMENT_COMPACTION_THRESHOLD", _EVERY)
    monkeypatch.setattr(stages35, "VERSION_CLEANUP_EVERY", _EVERY)


@pytest.mark.usefixtures("small_limits")
def test_the_ingest_stage_keeps_the_version_count_bounded(tmp_path: Path) -> None:
    ctx = _build(tmp_path)
    table = _table(ctx)
    assert table.count_rows() == 2 * _FILES
    # About two versions per file; at most one cleanup interval is left.
    assert len(table.list_versions()) <= 3 * _EVERY


@pytest.mark.usefixtures("small_limits")
def test_a_rebuild_gives_the_same_results_version_and_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _build(tmp_path / "build")
    rebuild = _build(tmp_path / "rebuild")
    monkeypatch.setattr(stages35, "VERSION_CLEANUP_EVERY", 10**9)
    kept = _build(tmp_path / "history-kept")
    # The seal's tokenizer record has its own test (test_experiment35_stages.py).
    monkeypatch.setattr(stages35.arms, "tokenizer_record", lambda settings, error: {})

    assert len(_table(kept).list_versions()) > 3 * _EVERY
    assert _ranked(first) == _ranked(rebuild) == _ranked(kept)
    # The cleanup deletes old versions only; the version number is the same.
    assert _table(first).version == _table(rebuild).version == _table(kept).version
    for ctx in (first, rebuild):
        assert asyncio.run(stages35.seal_stage(ctx)) == 0
        sealed = json.loads(
            ctx.layout.fingerprint(ctx.dataset, ctx.index).read_text(encoding="utf-8")
        )
        assert sealed["table_version"] == _table(ctx).version
        assert sealed["chunks"] == 2 * _FILES
