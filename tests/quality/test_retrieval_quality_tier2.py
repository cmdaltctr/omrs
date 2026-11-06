"""Real-llama.cpp Tier 2 retrieval-quality regression gate.

The gate runs OMRS's own llama.cpp embedding client (the ``llamacpp`` embedding
provider) against a llama.cpp server that serves one embedding model. The
nightly job starts that server; see the ``retrieval-quality-tier2`` job in
``.github/workflows/ci.yml`` for the exact command. To run the gate on a
machine, start a server the same way and run::

    uv run --no-sync pytest tests/quality/test_retrieval_quality_tier2.py -m slow -s

Set ``TIER2_LLAMACPP_URL`` when the server is not at ``http://127.0.0.1:8080``.
"""

from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.quality.runner import (
    CORPUS_DIR,
    assert_metric_floors,
    fixture_identities,
    load_baseline,
    load_golden_queries,
    measure_rows,
    measurement_record,
    validate_baseline,
)

from omrs.compose import (
    build_embed_model,
    build_vector_store,
    settings_to_effective,
)
from omrs.config import Settings
from omrs.core.ingestion import ingest_path_async
from omrs.core.retrieval import search
from omrs.core.retrieval.dense import _cached_query_embedding
from omrs.core.vectordb import set_default_store

pytestmark = pytest.mark.slow

#: The model the nightly job serves. It is the 0.6B build of the shipped embedding
#: family (the shipped default is the 4B build; the CPU runner has no GPU).
MODEL_TAG = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
SERVER_URL = os.environ.get("TIER2_LLAMACPP_URL", "http://127.0.0.1:8080").rstrip("/")
_COLLECTION = "quality_tier2"


def _server_json(path: str) -> dict[str, Any]:
    """Read one required llama.cpp server response or fail the gate."""
    try:
        with urllib.request.urlopen(  # noqa: S310 -- operator-set loopback URL
            f"{SERVER_URL}{path}",
            timeout=10,
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        pytest.fail(
            f"Tier 2 needs a llama.cpp server at {SERVER_URL} serving {MODEL_TAG} "
            f"(GET {path} failed: {exc}). Start llama-server as the "
            "retrieval-quality-tier2 job in .github/workflows/ci.yml does, "
            "or set TIER2_LLAMACPP_URL."
        )
    if not isinstance(payload, dict):
        pytest.fail(f"llama.cpp {path} returned a non-object response")
    return payload


def _server_identity() -> tuple[str, int]:
    """Return the server build and the served model's size in bytes, or fail the gate."""
    build = _server_json("/props").get("build_info")
    if not isinstance(build, str) or not build:
        pytest.fail("llama.cpp did not report a build in GET /props (build_info)")

    models = _server_json("/v1/models").get("data")
    if not isinstance(models, list):
        pytest.fail("llama.cpp did not report a model list in GET /v1/models")
    matches = [m for m in models if isinstance(m, dict) and m.get("id") == MODEL_TAG]
    if len(matches) != 1:
        pytest.fail(
            f"llama.cpp at {SERVER_URL} must list exactly one model {MODEL_TAG!r}; "
            f"it lists {[m.get('id') for m in models if isinstance(m, dict)]}"
        )
    meta = matches[0].get("meta")
    size = meta.get("size") if isinstance(meta, dict) else None
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        pytest.fail(f"llama.cpp model {MODEL_TAG!r} did not report meta.size in GET /v1/models")
    return build, size


async def _run_tier2(tmp_path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    llamacpp_build, model_size_bytes = _server_identity()
    config = Settings(
        # OMRS's real llama.cpp embedding client. The server is another process
        # (``external``), so OMRS does not start a router or check a model list.
        embed_provider="llamacpp",
        llamacpp_embed_model=MODEL_TAG,
        llamacpp_router_url=f"{SERVER_URL}/v1",
        llamacpp_router_server="external",
        vector_store="lancedb",
        lancedb_uri=str(tmp_path / "lancedb"),
        collection_name=_COLLECTION,
        pdf_reader="pypdf",
        chunking={"chunk_size": 1024, "chunk_overlap": 64},
        metadata={"extraction_mode": "disabled"},
        retrieval={
            "top_k": 10,
            "similarity_threshold": 0.0,
            "rerank_enabled": False,
            "rerank_enabled_for_semantic": False,
            "hybrid_enabled": True,
            "hybrid_rrf_k": 60,
            "hybrid_sparse_backend": "bm25",
        },
    )
    effective = settings_to_effective(config)
    store = build_vector_store(config)
    set_default_store(store)
    LlamaIndexSettings.embed_model = build_embed_model(config)
    _cached_query_embedding.cache_clear()

    ingest_result = await ingest_path_async(
        str(CORPUS_DIR),
        collection_name=_COLLECTION,
        effective_settings=effective,
    )
    assert ingest_result["status"] == "ok", ingest_result
    assert ingest_result["files_indexed"] == 20, ingest_result

    rows: list[dict[str, Any]] = []
    for query in load_golden_queries():
        results = search(
            query=query["query"],
            top_k=10,
            similarity_threshold=0.0,
            rerank=False,
            hybrid=True,
            collection_name=_COLLECTION,
            include_diagnostics=True,
            store=store,
            effective_settings=effective,
        )
        rows.append(
            {
                "id": query["id"],
                "query": query["query"],
                "expected_sources": query["expected_sources"],
                "sources": [result["source"] for result in results],
            }
        )

    corpus_id, query_set_id = fixture_identities()
    identity = {
        "model_tag": MODEL_TAG,
        "model_size_bytes": model_size_bytes,
        "llamacpp_build": llamacpp_build,
        "runner_os": platform.system(),
        "runner_architecture": platform.machine(),
        "corpus_id": corpus_id,
        "query_set_id": query_set_id,
    }
    return rows, identity


@pytest.mark.asyncio
async def test_tier2_quality_floors_and_identity(tmp_path) -> None:
    """Real llama.cpp retrieval remains above its identity-bound floors."""
    rows, identity = await _run_tier2(tmp_path)
    actual = measure_rows(rows)
    print(
        "TIER2_MEASUREMENT="
        + json.dumps(
            measurement_record(rows, extra=identity),
            sort_keys=True,
        )
    )

    baseline = load_baseline()
    validate_baseline(baseline, require_tier1=False, require_tier2=True)
    expected = baseline["tier2"]
    # The model identity binds the baseline: a silently repointed tag or a
    # different file under the same tag (a changed size) fails before metric
    # comparison.
    for field in ("model_tag", "model_size_bytes"):
        assert expected.get(field) == identity[field], (
            f"tier2 {field} mismatch: baseline={expected.get(field)!r}, "
            f"actual={identity[field]!r}. After a model or server change, "
            "re-measure and record the TIER2_MEASUREMENT values in tests/quality/baseline.json."
        )
    # llama.cpp build, OS, and architecture are recorded evidence, not pass
    # conditions: the nightly job runs a different pinned build on a different
    # OS and architecture, and the floor margin (TDR-016) exists to absorb
    # exactly that cross-platform ranking variation.
    for field in ("llamacpp_build", "runner_os", "runner_architecture"):
        assert isinstance(expected[field], str) and expected[field], (
            f"tier2 baseline {field} must record its measurement evidence"
        )
    assert baseline["corpus_id"] == identity["corpus_id"]
    assert baseline["query_set_id"] == identity["query_set_id"]
    assert_metric_floors(tier="tier2", actual=actual, baseline=baseline)
