"""The reranker's ONNX session uses bounded worker pools (ADR-118 rule)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omrs.core.retrieval import reranker as rr
from omrs.core.retrieval._reranker_cache import reset_model_cache


@pytest.fixture(autouse=True)
def _clean_cache() -> Any:
    reset_model_cache()
    yield
    reset_model_cache()


def _load(monkeypatch: pytest.MonkeyPatch, visible_cpus: int) -> dict[str, Any]:
    """Load the reranker with fakes and capture the session options."""
    monkeypatch.setattr(rr.os, "sched_getaffinity", lambda _pid: range(visible_cpus), raising=False)
    captured: dict[str, Any] = {}

    def _capture(path: str, providers: Any = None, sess_options: Any = None, **_kw: Any) -> Any:
        captured["options"] = sess_options
        return MagicMock()

    reranker = rr.CrossEncoderReranker(model_id="test/thread-cap")
    with (
        patch.object(rr, "_select_onnx_variant", return_value=["onnx/model.onnx"]),
        patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"),
        patch("tokenizers.Tokenizer.from_pretrained", return_value=MagicMock()),
        patch("onnxruntime.InferenceSession", side_effect=_capture),
        patch.object(rr, "_read_max_position_embeddings", return_value=512),
    ):
        reranker._load_model()
    assert reranker._loaded is True
    return captured


@pytest.mark.parametrize(("visible_cpus", "expected"), [(4, 4), (8, 8), (96, 8)])
def test_session_caps_intra_op_threads_and_uses_one_inter_op_thread(
    monkeypatch: pytest.MonkeyPatch, visible_cpus: int, expected: int
) -> None:
    options = _load(monkeypatch, visible_cpus)["options"]

    assert options is not None, "reranker built its ONNX session without SessionOptions"
    assert options.intra_op_num_threads == expected
    assert options.inter_op_num_threads == 1
