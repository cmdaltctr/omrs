"""Integration tests for reranking in retrieval: the rerank flag, threshold
scaling, failure fallback, rerank_reason diagnostics and the threshold that
follows the rerank outcome.

Split from ``test_retrieval.py`` so pytest-xdist can spread the slow
ingest-backed cases over more workers (``--dist loadfile``).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from conftest import connected_client, extract_tool_result, ingest_fixture_docs

# ── Rerank flag propagation ────────────────────────────────────────────────


async def test_default_search_uses_policy_resolver(mcp_server, fixtures_dir: Path) -> None:
    """Default MCP search uses policy resolver and preserves result shape."""
    async with connected_client(mcp_server) as client:
        await ingest_fixture_docs(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital"},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert "reranked" in r


async def test_rerank_false_sets_flag_false(mcp_server, fixtures_dir: Path) -> None:
    """Explicit rerank=False still preserves the un-reranked path."""
    async with connected_client(mcp_server) as client:
        await ingest_fixture_docs(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital", "rerank": False},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert r["reranked"] is False


async def test_rerank_enabled_sets_flag(mcp_server, fixtures_dir: Path) -> None:
    """With rerank=True, the reranked flag reflects actual reranker state."""
    async with connected_client(mcp_server) as client:
        await ingest_fixture_docs(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital", "rerank": True},
        )
        data = extract_tool_result(result)
        assert isinstance(data, list)
        # The reranked flag is True if the reranker loaded, False if it
        # fell back. Either way, the call must succeed.
        for r in data:
            assert "reranked" in r


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestPersistentRerankFailureFallback:
    """Regression: a permanently unavailable reranker must degrade gracefully.

    Mirrors the reranking spec scenario "persistent failure still falls
    back gracefully": search_documents with rerank=True must NOT crash or
    raise; it returns un-reranked results and emits a warning.
    """

    def setup_method(self) -> None:
        """Clear the process-wide model cache before each test.

        Earlier tests in this module (e.g. ``test_rerank_enabled_sets_flag``)
        exercise the un-injected ``search()`` path with no mocking, which
        may populate ``_MODEL_CACHE`` with a real successful load. Without
        this reset, the escalation test below would hit that cache instead
        of the patched failing import and never see a failure at all.
        """
        from omrs.core.retrieval.reranker import reset_model_cache

        reset_model_cache()

    def teardown_method(self) -> None:
        """Clear the process-wide model cache (task 1.13).

        ``test_transient_failure_retries_then_succeeds`` populates
        ``_MODEL_CACHE`` via ``_load_model()`` directly; without this reset
        the loaded session leaks into later tests, which becomes
        load-bearing once ``_FAILURE_STATE`` shares the same reset hook.
        """
        from omrs.core.retrieval.reranker import reset_model_cache

        reset_model_cache()

    async def test_persistent_failure_falls_back_without_crash(
        self, mcp_server, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A permanently failing reranker yields un-reranked results + warning."""

        import omrs.core.retrieval.reranker as reranker_mod
        from omrs.core.retrieval.reranker import CrossEncoderReranker

        # Build a reranker whose model load fails permanently.
        failing = CrossEncoderReranker(model_id="invalid/model-id")
        failing._loaded = False
        failing._load_attempted = True
        failing._load_error = "model permanently unavailable"

        # The retry path must also keep failing.
        def _fail_load(self) -> None:
            self._load_attempted = True
            self._load_error = "model permanently unavailable"

        monkeypatch.setattr(reranker_mod.CrossEncoderReranker, "_load_model", _fail_load)

        # Inject the failing reranker through the Engine that owns it.
        from conftest import build_mcp_server

        mcp_server = build_mcp_server(reranker=failing)

        async with connected_client(mcp_server) as client:
            await ingest_fixture_docs(client, fixtures_dir)
            result = await client.call_tool(
                "search_documents",
                {"query": "capital", "rerank": True},
            )
            data = extract_tool_result(result)
            assert isinstance(data, list)
            assert len(data) > 0
            # Graceful fallback: results returned, reranked flag False,
            # no error status dict.
            for r in data:
                assert "reranked" in r
                assert r["reranked"] is False

    async def test_escalation_survives_instance_churn_via_search(
        self,
        fixtures_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Escalation fires through the un-injected path (task 1.11).

        The test above injects a single failing instance via DI, so its
        instance state would accumulate across calls even if the counter
        were wrongly scoped to ``self`` — a green test over a broken
        production path (the exact ADR-029 trap). This test calls the
        core ``search()`` with ``reranker`` left un-injected so it builds
        a fresh ``CrossEncoderReranker()`` on every call, proving the
        counter survives instance churn.
        """
        import builtins
        import logging

        from omrs.core.ingestion import ingest_path_async
        from omrs.core.retrieval import search

        await ingest_path_async(str(fixtures_dir), collection_name="escalation_churn")

        real_import = builtins.__import__

        def _selective_import(name, *args, **kwargs):
            if name == "onnxruntime":
                raise ImportError("persistent onnx failure")
            return real_import(name, *args, **kwargs)

        with caplog.at_level(logging.WARNING, logger="omrs.core.retrieval.reranker"):
            with patch("builtins.__import__", side_effect=_selective_import):
                for _ in range(3):
                    search(
                        "capital",
                        collection_name="escalation_churn",
                        rerank=True,
                    )

        load_failure_records = [
            r for r in caplog.records if "Failed to load reranker model" in r.getMessage()
        ]
        assert len(load_failure_records) == 3
        assert [r.levelno for r in load_failure_records] == [
            logging.WARNING,
            logging.WARNING,
            logging.ERROR,
        ]

    def test_transient_failure_retries_then_succeeds(self) -> None:
        """A transient load failure must retry on the next call and recover."""
        from omrs.core.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(model_id="transient/model")
        reranker._loaded = False
        reranker._load_attempted = True
        reranker._load_error = "transient network timeout"

        mock_session = MagicMock()
        mock_tokenizer = MagicMock()

        with patch(
            "omrs.core.retrieval.reranker._select_onnx_variant", return_value=["onnx/model.onnx"]
        ):
            with patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"):
                with patch("tokenizers.Tokenizer.from_pretrained", return_value=mock_tokenizer):
                    with patch("onnxruntime.InferenceSession", return_value=mock_session):
                        with patch(
                            "omrs.core.retrieval.reranker._read_max_position_embeddings",
                            return_value=512,
                        ):
                            reranker._load_model()

        # Retry succeeded: model loaded, error cleared, cache populated.
        assert reranker._loaded is True
        assert reranker._load_error is None


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestThresholdScaling:
    """Tests for score-aware threshold scaling.

    When the reranker is active, sigmoid-normalised scores occupy a much
    lower range than cosine similarity.  The search() function should
    scale the threshold down by 30x automatically to avoid over-filtering.
    """

    def test_no_rerank_threshold_unchanged(self) -> None:
        """Without reranking, the threshold must not be scaled."""
        from omrs.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.3, rerank=False) == 0.3

    def test_rerank_threshold_scaled_down(self) -> None:
        """With reranking, the threshold must be scaled down 30x."""
        from omrs.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.3, rerank=True) == pytest.approx(0.01)

    def test_zero_threshold_stays_zero_no_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero without rerank."""
        from omrs.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.0, rerank=False) == 0.0

    def test_zero_threshold_stays_zero_with_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero with rerank."""
        from omrs.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.0, rerank=True) == 0.0

    def test_moderate_threshold_with_rerank(self) -> None:
        """A moderate threshold (0.5) should become ~0.0167 with rerank."""
        from omrs.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.5, rerank=True) == pytest.approx(0.5 / 30)

    def test_colosseum_score_survives_threshold(self) -> None:
        """The Colosseum query (score 0.015) must survive threshold 0.3.

        This was the motivating case: the reranker correctly identified
        the Colosseum chunk but gave it a low sigmoid score (0.015).
        With 30x scaling, threshold 0.3 → 0.01, so 0.015 passes.
        """
        from omrs.core.retrieval.policy import _effective_threshold

        threshold = _effective_threshold(0.3, rerank=True)
        assert 0.015 >= threshold  # Colosseum score should pass


# ── Helpers for §2/§3 pipeline-level tests ──────────────────────────────────


def _fixed_dense_rows(rows: list[dict]):
    """Return a fake ``_dense_query_rows`` callable yielding fixed rows."""

    # Accepts the norm-guard and timing keyword arguments the real dense
    # boundary receives (guard-embedding-normalisation,
    # complete-observable-surface); the fake never runs them. The
    # query_instruction kwarg is likewise accepted and discarded: the
    # fake returns fixed rows, so the model-facing query text is
    # irrelevant here (query-embedding-preparation).
    def _fake(
        store,
        collection_name,
        query,
        fetch_k,
        metadata_filter=None,
        *,
        norm_guard_enabled=True,
        norm_tolerance=0.001,
        attach_norm_diagnostic=False,
        timing_report=None,
        embed_model=None,
        cache=None,
        query_instruction="",
    ):
        return [dict(r) for r in rows]

    return _fake


def _patch_dense(monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
    """Replace pipeline's "dense" strategy resolution with fixed rows.

    The registry caches resolved callables by name (``registry.py::get``),
    so patching ``omrs.core.retrieval.dense._dense_query_rows`` after
    the first real resolution elsewhere in the suite would be a no-op.
    Patching ``pipeline._retrieval_get`` itself sidesteps that cache.
    """
    import omrs.core.retrieval.pipeline as pipeline_mod

    real_get = pipeline_mod._retrieval_get
    monkeypatch.setattr(
        pipeline_mod,
        "_retrieval_get",
        lambda name: _fixed_dense_rows(rows) if name == "dense" else real_get(name),
    )


def _mock_reranker_instance(*, fails: bool, logit: float = -3.0):
    """Build a loaded ``CrossEncoderReranker`` whose inference succeeds or fails."""
    from omrs.core.retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    mock_session = MagicMock()
    if fails:
        mock_session.run.side_effect = RuntimeError("cross-encoder exploded")
    else:
        mock_session.run.return_value = [np.array([[logit]])]
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": [[1, 2]],
        "attention_mask": [[1, 1]],
    }
    reranker._session = mock_session
    reranker._tokenizer = mock_tokenizer
    reranker._loaded = True
    return reranker


# ── rerank_reason diagnostics (§2) ───────────────────────────────────────────


class TestRerankReasonDiagnostics:
    """Tests for surfacing the reranker's own failure reason in diagnostics."""

    def test_failing_reranker_overrides_policy_rerank_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing reranker's own reason replaces the policy string (task 2.3)."""
        from omrs.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.9,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            include_diagnostics=True,
        )

        assert len(results) == 1
        assert "inference failed" in results[0]["rerank_reason"]
        assert "cross-encoder exploded" in results[0]["rerank_reason"]
        # Must not be the policy resolver's string.
        assert "explicit rerank=True override" not in results[0]["rerank_reason"]

    def test_include_diagnostics_false_leaks_no_new_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """include_diagnostics=False keeps result shape unchanged (task 2.4).

        Exercised with a *failing* reranker specifically — the override
        wiring must not leak ``rerank_reason`` (or any other new key)
        into the public result dict when diagnostics are off, even
        though the reranker did set ``last_failure_reason`` internally.
        """
        from omrs.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.9,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            include_diagnostics=False,
        )

        assert len(results) == 1
        assert "rerank_reason" not in results[0]


# ── Threshold follows rerank outcome, not intent (§3) ───────────────────────


class TestThresholdFollowsRerankOutcome:
    """Tests that the ÷30 threshold scaling follows actual rerank success."""

    def test_successful_rerank_applies_scaled_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful reranking still applies the ÷30 threshold (task 3.2)."""
        from omrs.core.retrieval import search

        # score=0.2 dense/raw would fail an unscaled 0.3 threshold, but the
        # reranker replaces it with a sigmoid score (logit -3.0 -> ~0.047),
        # which survives the scaled threshold (0.3 / 30 = 0.01).
        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        succeeding = _mock_reranker_instance(fails=False, logit=-3.0)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=succeeding,
            similarity_threshold=0.3,
        )

        assert len(results) == 1
        assert results[0]["reranked"] is True

    def test_failed_rerank_applies_unscaled_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed reranker filters at the caller's raw threshold (task 3.3).

        Regression guard for the bug this change fixes: before the fix,
        ``_effective_threshold`` was called with the *requested* rerank
        intent rather than the outcome, so a failed rerank kept scoring
        raw cosine similarity while filtering at the ÷30-scaled threshold
        — about 30x too permissive.
        """
        from omrs.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            similarity_threshold=0.3,
        )

        # Raw score 0.2 < unscaled threshold 0.3 -> filtered out.
        assert results == []

    def test_rerank_false_applies_unscaled_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """rerank=False applies the unscaled threshold, unchanged (task 3.4)."""
        from omrs.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=False,
            similarity_threshold=0.3,
        )

        # Raw score 0.2 < unscaled threshold 0.3 -> filtered out.
        assert results == []
