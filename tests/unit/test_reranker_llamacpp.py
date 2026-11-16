"""The llama.cpp reranker backend (design D27, tasks 12.1 to 12.5).

The backend sends one ``POST {router}/v1/rerank`` per query. Tests talk to a
stub HTTP server on a free port, never to a real model.
"""

from __future__ import annotations

import json
import math
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

import pytest

from omrs.core.retrieval._reranker_cache import reset_model_cache

MODEL = "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF:Q8_0"


@pytest.fixture(autouse=True)
def _reset_cache() -> Iterator[None]:
    reset_model_cache()
    yield
    reset_model_cache()


class _StubRouter:
    """A stub llama.cpp router: records each request, replies from ``reply``."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.status = 200
        # Default reply: score each document by a fixed list, as llama.cpp does,
        # sorted by score (the server sorts its results).
        self.reply = self._scored

    def _scored(self, body: dict[str, Any]) -> dict[str, Any]:
        documents = body["documents"]
        scores = [round(1.0 - i / (len(documents) + 1), 6) for i in range(len(documents))]
        scores.reverse()  # the last document scores highest
        results = [{"index": i, "relevance_score": s} for i, s in enumerate(scores)]
        results.sort(key=lambda r: r["relevance_score"], reverse=True)
        return {"model": body["model"], "results": results}

    def serve(self) -> Iterator[str]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append((self.path, body))
                payload = json.dumps(stub.reply(body)).encode()
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args: Any) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/v1"
        finally:
            server.shutdown()
            server.server_close()


@pytest.fixture
def stub() -> _StubRouter:
    return _StubRouter()


@pytest.fixture
def router_url(stub: _StubRouter) -> Iterator[str]:
    yield from stub.serve()


def _rows(n: int) -> list[dict[str, Any]]:
    return [{"text": f"passage {i}", "score": 0.5, "chunk_id": f"c{i}"} for i in range(n)]


def _reranker(url: str):
    from omrs.core.retrieval.reranker_llamacpp import LlamaCppReranker

    return LlamaCppReranker(model_id=MODEL, router_url=url)


# ── 12.1 Registry, backend map and accepted value ─────────────────────────


def test_registry_resolves_class_without_importing_the_module() -> None:
    sys.modules.pop("omrs.core.retrieval.reranker_llamacpp", None)
    from omrs.core.retrieval import registry

    assert "omrs.core.retrieval.reranker_llamacpp" not in sys.modules
    cls = registry.get("reranker_llamacpp")
    assert cls.__name__ == "LlamaCppReranker"
    assert cls.backend_name == "llamacpp"


def test_backend_map_resolves_llamacpp_and_refuses_vllm() -> None:
    from omrs.core.retrieval.backend import resolve_reranker_backend
    from omrs.core.retrieval.reranker_llamacpp import LlamaCppReranker

    assert resolve_reranker_backend("llamacpp") is LlamaCppReranker
    with pytest.raises(KeyError) as refusal:
        resolve_reranker_backend("vllm")
    for name in ("onnx", "torch", "llamacpp"):
        assert name in str(refusal.value)


def test_settings_accept_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.config import Settings

    monkeypatch.setenv("RETRIEVAL__RERANK_BACKEND", "llamacpp")
    assert Settings().retrieval.rerank_backend == "llamacpp"


def test_settings_refuse_unknown_backend_naming_all_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrs.config import Settings

    monkeypatch.setenv("RETRIEVAL__RERANK_BACKEND", "vllm")
    with pytest.raises(ValueError, match="Accepted values: onnx, torch, llamacpp"):
        Settings()


# ── 12.2 The HTTP call ────────────────────────────────────────────────────


def test_one_post_per_query_with_model_query_and_texts_in_order(
    stub: _StubRouter, router_url: str
) -> None:
    _reranker(router_url).rerank("what is x", _rows(3), top_k=3)

    assert stub.requests == [
        (
            "/v1/rerank",
            {
                "model": MODEL,
                "query": "what is x",
                "documents": ["passage 0", "passage 1", "passage 2"],
            },
        )
    ]


def test_results_sorted_truncated_and_flagged(stub: _StubRouter, router_url: str) -> None:
    reranker = _reranker(router_url)
    result = reranker.rerank("q", _rows(5), top_k=3)

    assert [row["chunk_id"] for row in result] == ["c4", "c3", "c2"]
    assert all(row["_reranked"] is True for row in result)
    assert all(0.0 < row["score"] <= 1.0 for row in result)
    assert reranker.last_failure_reason is None


def test_score_is_the_server_probability_unchanged(stub: _StubRouter, router_url: str) -> None:
    """llama.cpp b11941 applies softmax for Qwen3 in rank pooling, and
    ``send_rerank`` returns ``embd[0]`` with no further transform, so
    ``relevance_score`` is a probability in [0, 1]. A zero (float underflow)
    becomes the smallest positive float, so every score is in (0, 1]."""
    stub.reply = lambda body: {
        "results": [
            {"index": 1, "relevance_score": 0.91},
            {"index": 2, "relevance_score": 0.5},
            {"index": 0, "relevance_score": 0.07},
            {"index": 3, "relevance_score": 0.0},
        ]
    }
    result = _reranker(router_url).rerank("q", _rows(4), top_k=4)

    assert [(row["chunk_id"], row["score"]) for row in result] == [
        ("c1", 0.91),
        ("c2", 0.5),
        ("c0", 0.07),
        ("c3", math.ulp(0.0)),
    ]


def test_score_outside_the_probability_range_is_a_bad_reply(
    stub: _StubRouter, router_url: str
) -> None:
    """A raw logit means a different server build: never mix it in."""
    stub.reply = lambda body: {
        "results": [{"index": 0, "relevance_score": 3.2}, {"index": 1, "relevance_score": -1.4}]
    }
    reranker = _reranker(router_url)
    result = reranker.rerank("q", _rows(2), top_k=2)

    assert [row["_reranked"] for row in result] == [False, False]
    assert "relevance_score" in (reranker.last_failure_reason or "")


def test_empty_candidates_send_no_call(stub: _StubRouter, router_url: str) -> None:
    assert _reranker(router_url).rerank("q", [], top_k=5) == []
    assert stub.requests == []


def _assert_unreranked(reranker: Any, result: list[dict[str, Any]], top_k: int) -> None:
    assert [row["chunk_id"] for row in result] == [f"c{i}" for i in range(top_k)]
    assert all(row["_reranked"] is False for row in result)
    assert all(row["score"] == 0.5 for row in result)
    assert reranker.last_failure_reason


def test_refused_connection_returns_inputs_unreranked() -> None:
    reranker = _reranker("http://127.0.0.1:9/v1")
    _assert_unreranked(reranker, reranker.rerank("q", _rows(4), top_k=2), 2)


def test_http_500_returns_inputs_unreranked(stub: _StubRouter, router_url: str) -> None:
    stub.status = 500
    stub.reply = lambda body: {"error": {"message": "boom"}}
    reranker = _reranker(router_url)
    _assert_unreranked(reranker, reranker.rerank("q", _rows(4), top_k=2), 2)


def test_unknown_model_returns_inputs_unreranked(stub: _StubRouter, router_url: str) -> None:
    stub.status = 400
    stub.reply = lambda body: {"error": {"message": "model not found"}}
    reranker = _reranker(router_url)
    _assert_unreranked(reranker, reranker.rerank("q", _rows(3), top_k=3), 3)


def test_reply_with_missing_index_returns_inputs_unreranked(
    stub: _StubRouter, router_url: str
) -> None:
    stub.reply = lambda body: {"results": [{"index": 0, "relevance_score": 0.9}]}
    reranker = _reranker(router_url)
    _assert_unreranked(reranker, reranker.rerank("q", _rows(3), top_k=3), 3)
    assert "scored indexes [0] for 3 documents" in (reranker.last_failure_reason or "")


def test_failure_reason_resets_on_the_next_good_call(stub: _StubRouter, router_url: str) -> None:
    reranker = _reranker(router_url)
    stub.status = 500
    reranker.rerank("q", _rows(2), top_k=2)
    assert reranker.last_failure_reason
    stub.status = 200
    stub.reply = stub._scored
    reranker.rerank("q", _rows(2), top_k=2)
    assert reranker.last_failure_reason is None


# ── 12.3 Construction ─────────────────────────────────────────────────────


def test_build_from_settings_uses_from_settings(effective_settings) -> None:
    from omrs.core.retrieval.backend import build_reranker_from_settings
    from omrs.core.retrieval.reranker_llamacpp import LlamaCppReranker

    settings = effective_settings(
        rerank_backend="llamacpp", rerank_model=MODEL, llamacpp_router_url="http://router:8080/v1"
    )
    with patch.object(
        LlamaCppReranker, "from_settings", wraps=LlamaCppReranker.from_settings
    ) as from_settings:
        reranker = build_reranker_from_settings(settings)

    from_settings.assert_called_once_with(settings)
    assert isinstance(reranker, LlamaCppReranker)
    assert (reranker.model_id, reranker.router_url) == (MODEL, "http://router:8080/v1")


@pytest.mark.parametrize("backend", ["onnx", "torch"])
def test_onnx_and_torch_keep_the_model_id_constructor(backend: str, effective_settings) -> None:
    from omrs.core.retrieval import backend as backend_mod

    calls: list[dict[str, Any]] = []

    class _Fake:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    settings = effective_settings(rerank_backend=backend, rerank_model="some/model")
    with patch.object(backend_mod, "resolve_reranker_backend", return_value=_Fake):
        backend_mod.build_reranker_from_settings(settings)

    assert calls == [{"model_id": "some/model"}]


def test_compose_and_lazy_paths_build_the_same_backend(effective_settings) -> None:
    from omrs.compose import build_reranker
    from omrs.core.retrieval.backend import build_reranker_from_settings

    settings = effective_settings(
        rerank_backend="llamacpp", rerank_model=MODEL, llamacpp_router_url="http://router:8080/v1"
    )
    injected = build_reranker(settings)
    lazy = build_reranker_from_settings(settings)

    assert type(injected) is type(lazy)
    assert (injected.model_id, injected.router_url) == (lazy.model_id, lazy.router_url)
    assert (lazy.model_id, lazy.router_url) == (MODEL, "http://router:8080/v1")


# ── 12.4 A rank entry in the router list ──────────────────────────────────


def test_unassigned_rank_entry_gives_no_role_problem_and_is_written(tmp_path) -> None:
    from omrs.config.llamacpp_models import SHIPPED_MODELS, check_model_entry
    from omrs.config.llamacpp_roles import derive_roles
    from omrs.integrations.llamacpp_runtime.hashes import HashCache
    from omrs.integrations.llamacpp_runtime.preset_writer import plan_preset

    gguf = tmp_path / "qwen3-reranker-0.6b-q8_0.gguf"
    gguf.write_bytes(b"GGUF data")
    entry, problems = check_model_entry(
        {
            "model": MODEL,
            "file": str(gguf),
            "preset": {
                "embeddings": True,
                "pooling": "rank",
                "ctx-size": 8192,
                "batch-size": 8192,
                "ubatch-size": 8192,
            },
        }
    )
    assert problems == [] and entry is not None
    models = {**SHIPPED_MODELS, "qwen3-reranker-0.6b": entry}

    report = derive_roles(
        models,
        embed_model=SHIPPED_MODELS["qwen3-embedding-4b"].model,
        classify_model=SHIPPED_MODELS["qwen3-4b"].model,
    )
    assert report.problems == ()
    assert report.roles["qwen3-reranker-0.6b"] == ()

    plan = plan_preset([entry], hashes=HashCache(tmp_path / "state" / "hashes.json"))
    assert plan.outcome(MODEL).state == "listed"  # type: ignore[union-attr]
    assert f"[{MODEL}]\n" in plan.text
    assert "embeddings = true\n" in plan.text
    assert "pooling = rank\n" in plan.text


# ── 12.5 End to end through search ────────────────────────────────────────


def test_search_reranks_the_pool_through_the_router(
    stub: _StubRouter, router_url: str, tmp_path, effective_settings
) -> None:
    from omrs.core.retrieval.pipeline import search
    from omrs.core.vectordb.identity import EmbeddingIdentity
    from omrs.core.vectordb.lancedb.store import LanceVectorStore

    identity = EmbeddingIdentity(provider="test", model="fixed")
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=identity)
    count = 120
    store.upsert_precomputed(
        "docs",
        [f"c{i}" for i in range(count)],
        [f"passage {i}" for i in range(count)],
        [{"file_path": f"/d/{i}.txt", "chunk_id": f"c{i}"} for i in range(count)],
        [[math.cos(0.01 * i), math.sin(0.01 * i), 0.0, 0.0] for i in range(count)],
        embedding_identity=identity,
    )

    class _Embed:
        model_name = "fixed"

        def get_query_embedding(self, _query: str) -> list[float]:
            return [1.0, 0.0, 0.0, 0.0]

    settings = effective_settings(
        rerank_backend="llamacpp",
        rerank_model=MODEL,
        llamacpp_router_url=router_url,
        similarity_threshold=0.0,
    )
    rows = search(
        "q",
        top_k=10,
        rerank=True,
        hybrid=False,
        collection_name="docs",
        store=store,
        effective_settings=settings,
        embed_model=_Embed(),
        include_diagnostics=True,
    )

    ((path, body),) = stub.requests
    assert path == "/v1/rerank" and body["model"] == MODEL
    assert len(body["documents"]) == 100
    assert body["documents"][:2] == ["passage 0", "passage 1"]
    # The stub scores the last candidate highest, so rerank reverses the pool.
    assert [row["chunk_id"] for row in rows] == [f"c{i}" for i in range(99, 89, -1)]
    assert all(row["reranked"] is True for row in rows)
    assert {row["rerank_backend"] for row in rows} == {"llamacpp"}
