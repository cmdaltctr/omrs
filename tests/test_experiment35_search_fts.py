"""Experiment 35 search stage on a real LanceDB collection (task 5.5).

Rules under test: a hybrid search stage on a sealed collection leaves the
table version and the full-text index counts unchanged, with the ``bm25`` and
the ``native`` sparse backend (the read-only OMRS query of task 0.5); a
``native`` stage on a collection with no full-text index refuses before the
first query. The search is the real OMRS retrieval pipeline; only the query
embedding is a stub. No model and no network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import lancedb
import pytest
from tests._exp35_fixtures import load, stage_ctx

from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.core.vectordb.lancedb.fts import ensure_fts_index, fts_index_stats

datasets35 = load("datasets35")
outputs35 = load("outputs35")
search35 = load("search35")
stagekit35 = load("stagekit35")

HYBRID = "e4b-c1024-roff-hon"
_IDENTITY = EmbeddingIdentity(provider="test", model="mock")
_CORPUS = [
    ("c0", "the colosseum of ancient rome", "rome.md"),
    ("c1", "quantum computing with qubits", "quantum.md"),
    ("c2", "modern stadium concrete design", "stadium.md"),
]


def _questions() -> list[Any]:
    return [
        datasets35.Question(qid="q0", text="colosseum rome", relevant=()),
        datasets35.Question(qid="q1", text="quantum qubits", relevant=()),
    ]


class _Engine:
    """The real OMRS search on one store; records each query and the sparse backend served."""

    def __init__(self, store: Any, settings: Any) -> None:
        self.store = store
        self.settings = settings
        self.calls: list[str] = []
        self.backends: set[str | None] = set()

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        import omrs.core.retrieval.pipeline as retrieval

        self.calls.append(text)
        rows = retrieval.search(text, store=self.store, effective_settings=self.settings, **kwargs)
        self.backends.update(row.get("sparse_backend") for row in rows)
        return rows


def _table(ctx: Any) -> Any:
    return lancedb.connect(str(ctx.layout.store(ctx.index))).open_table(ctx.collection)


def _sealed(ctx: Any, backend: str, *, fts: bool = True) -> Any:
    """Replace the fixture table with an OMRS-written collection and seal it for *backend*."""
    from omrs.core.vectordb.lancedb.store import LanceVectorStore

    uri = str(ctx.layout.store(ctx.index))
    lancedb.connect(uri).drop_table(ctx.collection)
    store = LanceVectorStore(uri=uri)
    store.upsert_precomputed(
        ctx.collection,
        [row_id for row_id, _, _ in _CORPUS],
        [text for _, text, _ in _CORPUS],
        [{"file_name": name} for _, _, name in _CORPUS],
        [[0.5, 0.5, 0.5, 0.5]] * len(_CORPUS),
        embedding_identity=_IDENTITY,
    )
    if fts:
        ensure_fts_index(store._open_table(ctx.collection))
    outputs35.write_json(
        ctx.layout.fingerprint(ctx.dataset, ctx.index),
        {
            "collection": ctx.collection,
            "table_version": _table(ctx).version,
            "sparse_backend": backend,
        },
    )
    ctx.settings.retrieval.hybrid_sparse_backend = backend
    return store


@pytest.fixture
def stub_query_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    import omrs.core.retrieval.dense as dense
    from omrs.core.retrieval.sparse_dispatch import reset_warning_state

    monkeypatch.setattr(dense, "_embed_query", lambda _q, _em=None, _c=None: [0.5] * 4)
    reset_warning_state()


def _settings(effective_settings: Any, backend: str) -> Any:
    return effective_settings(
        hybrid_enabled=True,
        hybrid_sparse_backend=backend,
        rerank_enabled=False,
        similarity_threshold=0.0,
    )


@pytest.mark.usefixtures("stub_query_embedding")
@pytest.mark.parametrize("backend", ["bm25", "native"])
def test_a_hybrid_search_stage_leaves_the_table_version_and_fts_counts_unchanged(
    tmp_path: Path, effective_settings: Any, backend: str
) -> None:
    ctx = stage_ctx(tmp_path, "search", HYBRID, kind="search", questions=_questions())
    store = _sealed(ctx, backend)
    before = (_table(ctx).version, fts_index_stats(_table(ctx)))
    assert before[1] == (len(_CORPUS), 0)
    ctx.engine = _Engine(store, _settings(effective_settings, backend))

    assert asyncio.run(search35.search_stage(ctx)) == 0

    assert ctx.engine.calls == ["colosseum rome", "quantum qubits"]
    assert ctx.engine.backends == {backend}  # the hybrid path ran on this backend, no fallback
    assert (_table(ctx).version, fts_index_stats(_table(ctx))) == before
    marker = json.loads((ctx.run_dir / ".done-search.json").read_text(encoding="utf-8"))
    assert marker["checks"]["table_version_unchanged"] is True
    assert marker["checks"]["fingerprint"]["table_version"] == before[0]
    assert marker["checks"]["fingerprint"]["sparse_backend"] == backend
    assert marker["checks"]["fingerprint"]["fts"] is not None


@pytest.mark.usefixtures("stub_query_embedding")
def test_a_native_stage_on_a_collection_with_no_fts_index_refuses_before_the_first_query(
    tmp_path: Path, effective_settings: Any
) -> None:
    ctx = stage_ctx(tmp_path, "search", HYBRID, kind="search", questions=_questions())
    store = _sealed(ctx, "native", fts=False)
    ctx.engine = _Engine(store, _settings(effective_settings, "native"))

    with pytest.raises(stagekit35.FingerprintError, match="no full-text index for the native"):
        asyncio.run(search35.search_stage(ctx))

    assert ctx.engine.calls == []
    assert not (ctx.run_dir / "search.jsonl").exists() or not (
        ctx.run_dir / "search.jsonl"
    ).read_text(encoding="utf-8")
    assert not (ctx.run_dir / ".done-search.json").exists()
    assert fts_index_stats(_table(ctx)) is None
