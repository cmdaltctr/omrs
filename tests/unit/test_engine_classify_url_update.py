"""A classification address change applies to the next classification (ADR-108 D2).

``Engine.use_provider_settings`` takes a new ``llamacpp_classify_url`` with no
restart, because the address is a provider address field. The next llama.cpp
classification request goes to the new address.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async
from omrs.core.settings import MetadataBlock
from omrs.engine import Engine


@pytest.mark.metadata_llm
def test_the_next_classification_uses_the_new_address(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        content = '{"category": "report", "keywords": [], "summary": ""}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}),
    )
    first = effective_settings(
        llamacpp_chat_url="http://127.0.0.1:8081/v1",
        metadata=MetadataBlock(classify_max_attempts=1),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    engine = Engine(first, store=store, embed_model=MagicMock(model_name="test-model"))
    try:
        engine.use_provider_settings(
            first.model_copy(update={"llamacpp_classify_url": "http://127.0.0.1:9931/v1"})
        )
        effective, _ = engine._resolve_bound("docs")
        asyncio.run(_extract_llamacpp_chat_async("text", "f.txt", effective))
    finally:
        engine.close()

    assert urls == ["http://127.0.0.1:9931/v1/chat/completions"]
