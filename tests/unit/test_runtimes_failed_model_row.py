"""A model whose load failed shows ``failed`` in ``GET /v1/runtimes`` (PR 185 review).

llama.cpp b11941 reports a failed load as ``unloaded`` with ``failed: true``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from omrs import compose_runtimes
from omrs.integrations.llamacpp_runtime.spec import RuntimeSpec

MODEL = "Qwen/Qwen3-4B-GGUF:Q8_0"


def _rows(monkeypatch: pytest.MonkeyPatch, status: dict[str, Any]) -> list[dict[str, Any]]:
    entry = SimpleNamespace(model=MODEL, file="", preset={})
    settings = SimpleNamespace(llamacpp_models={"qwen3-4b": entry})
    monkeypatch.setattr(compose_runtimes, "_live_models", lambda spec, item: {MODEL: status})
    monkeypatch.setattr(
        compose_runtimes, "_roles", lambda s: SimpleNamespace(roles={}, problems=())
    )
    monkeypatch.setattr(compose_runtimes, "managed_decision_models", lambda s: {})
    spec = RuntimeSpec(id="router", role="router", mode="external", binary="")
    return list(compose_runtimes._model_rows(settings, spec, {"state": "running"}))


def test_a_failed_load_row_reads_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(monkeypatch, {"value": "unloaded", "failed": True, "exit_code": 1})
    assert rows[0]["state"] == "failed"


def test_a_loaded_model_row_reads_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _rows(monkeypatch, {"value": "loaded"})[0]["state"] == "loaded"
