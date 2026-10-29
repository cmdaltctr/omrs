"""Classification and Chat stay apart on llama.cpp (ADR-108, design D2 and D3).

Classification uses the classification address, which follows the Chat
address until a source sets it. An answer role never falls back to the
Text model (classification).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from omrs.core.providers.llm import llamacpp
from omrs.core.providers.llm.llamacpp import classification_url
from omrs.core.settings import EffectiveSettings, MetadataBlock

CHAT = "http://localhost:8081/v1"
CLASSIFY = "http://127.0.0.1:9931/v1"


def settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "llamacpp_chat_url": CHAT,
        "llamacpp_classify_url": "",
        "llamacpp_chat_model": "Qwen/Qwen3-0.6B-GGUF:Q8_0",
        "llamacpp_embed_url": "http://localhost:8080/v1",
        "metadata": SimpleNamespace(classify_timeout=30.0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_classification_address_follows_the_chat_address(blank: str) -> None:
    assert classification_url(settings(llamacpp_classify_url=blank)) == CHAT


def test_a_set_classification_address_is_used() -> None:
    assert classification_url(settings(llamacpp_classify_url=CLASSIFY)) == CLASSIFY


# ── Builder roles (design D3) ─────────────────────────────────────────────


class RecordingOpenAILike:
    """Records the keyword arguments of each construction."""

    built: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        RecordingOpenAILike.built.append(kwargs)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import llama_index.llms.openai_like as module

    RecordingOpenAILike.built = []
    monkeypatch.setattr(module, "OpenAILike", RecordingOpenAILike)
    return RecordingOpenAILike.built


def test_no_answer_model_means_classification(recorded: list[dict[str, Any]]) -> None:
    llamacpp.build(settings(llamacpp_classify_url=CLASSIFY))
    assert (recorded[0]["api_base"], recorded[0]["model"]) == (
        CLASSIFY,
        "Qwen/Qwen3-0.6B-GGUF:Q8_0",
    )


def test_classification_follows_the_chat_address_while_blank(
    recorded: list[dict[str, Any]],
) -> None:
    llamacpp.build(settings())
    assert recorded[0]["api_base"] == CHAT


def test_an_answer_model_goes_to_the_chat_address(recorded: list[dict[str, Any]]) -> None:
    llamacpp.build(settings(llamacpp_classify_url=CLASSIFY), answer_model="Qwen/Qwen3-4B-GGUF")
    assert (recorded[0]["api_base"], recorded[0]["model"]) == (CHAT, "Qwen/Qwen3-4B-GGUF")


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_answer_model_is_refused_and_builds_nothing(
    recorded: list[dict[str, Any]], blank: str
) -> None:
    with pytest.raises(ValueError, match=r"Settings > Chat"):
        llamacpp.build(settings(), answer_model=blank)
    assert recorded == []


# ── Classification requests go to the classification address (3.2) ───────


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = '{"category": "report", "keywords": ["a"], "summary": "s"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests


def _effective(**overrides: Any) -> EffectiveSettings:
    return EffectiveSettings(
        llamacpp_chat_url="http://127.0.0.1:8081/v1",
        llamacpp_chat_model="Qwen/Qwen3-0.6B-GGUF:Q8_0",
        metadata=MetadataBlock(classify_max_attempts=1),
        **overrides,
    )


@pytest.mark.metadata_llm
def test_direct_classification_uses_the_classification_address(
    captured: list[httpx.Request],
) -> None:
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    resolved = _effective(llamacpp_classify_url="http://127.0.0.1:9931/v1")
    asyncio.run(_extract_llamacpp_chat_async("text", "f.txt", resolved))
    (request,) = captured
    assert str(request.url) == "http://127.0.0.1:9931/v1/chat/completions"
    assert json.loads(request.content)["model"] == "Qwen/Qwen3-0.6B-GGUF:Q8_0"
    assert all(r.url.port != 8081 for r in captured)


@pytest.mark.metadata_llm
def test_direct_classification_follows_the_chat_address_while_blank(
    captured: list[httpx.Request],
) -> None:
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    asyncio.run(_extract_llamacpp_chat_async("text", "f.txt", _effective()))
    assert str(captured[0].url) == "http://127.0.0.1:8081/v1/chat/completions"


@pytest.mark.metadata_llm
def test_llamaindex_classification_builds_on_the_classification_address(
    recorded: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.metadata import extractor, llamaindex

    async def local(*_: Any, **__: Any) -> dict[str, Any]:
        return {"category": "uncategorised", "keywords": [], "summary": ""}

    monkeypatch.setattr(extractor, "_dispatch_local_extraction", local)
    resolved = _effective(
        llamacpp_classify_url="http://127.0.0.1:9931/v1",
        metadata_llm_provider="local",
        local_backend="llamacpp",
    )
    asyncio.run(llamaindex._extract_llamaindex_async("text", "f.txt", resolved))
    assert recorded[0]["api_base"] == "http://127.0.0.1:9931/v1"
    assert recorded[0]["model"] == "Qwen/Qwen3-0.6B-GGUF:Q8_0"
