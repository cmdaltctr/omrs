"""The llama.cpp model is called through the chat endpoint (TDR-037 pattern).

``OpenAILike`` defaults to ``is_chat_model=False``, which sends every call to
the legacy ``/completions`` endpoint with raw text. The server then applies no
chat template and no stop token, so a small model runs to the context limit.
Both roles must use ``/chat/completions``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from omrs.core.providers.llm import llamacpp

BASE = "http://127.0.0.1:9931/v1"


@pytest.fixture
def _settings(effective_settings: Callable[..., Any]) -> Any:
    return effective_settings(
        llamacpp_router_url=BASE,
        llamacpp_router_server="external",
        llamacpp_chat_model="Qwen/Qwen3-0.6B-GGUF:Q8_0",
        **{"metadata.classify_timeout": 30.0},
    )


_CHAT_REPLY = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "m",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "A Title",
                "reasoning_content": "thinking about it",
            },
        }
    ],
    "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
}


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Route the LLM's HTTP calls to a stub server and record each request."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json=_CHAT_REPLY)
        return httpx.Response(200, json={"error": "legacy endpoint"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        llamacpp,
        "http_clients",
        lambda role: {
            "http_client": httpx.Client(transport=transport),
            "async_http_client": httpx.AsyncClient(transport=transport),
        },
    )
    return seen


@pytest.mark.parametrize("answer_model", [None, "m"])
def test_build_declares_a_chat_model(_settings: Any, answer_model: str | None) -> None:
    llm = llamacpp.build(_settings, answer_model=answer_model)
    assert llm.is_chat_model is True
    assert llm.metadata.is_chat_model is True


@pytest.mark.parametrize("answer_model", [None, "m"])
def test_complete_uses_the_chat_endpoint(
    _settings: Any, monkeypatch: pytest.MonkeyPatch, answer_model: str | None
) -> None:
    seen = _wire(monkeypatch)
    llm = llamacpp.build(_settings, answer_model=answer_model)

    reply = llm.complete("question")

    assert [r.url.path for r in seen] == ["/v1/chat/completions"]
    assert reply.text == "A Title"


@pytest.mark.asyncio
@pytest.mark.parametrize("answer_model", [None, "m"])
async def test_acomplete_uses_the_chat_endpoint(
    _settings: Any, monkeypatch: pytest.MonkeyPatch, answer_model: str | None
) -> None:
    seen = _wire(monkeypatch)
    llm = llamacpp.build(_settings, answer_model=answer_model)

    reply = await llm.acomplete("question")

    assert [r.url.path for r in seen] == ["/v1/chat/completions"]
    assert reply.text == "A Title"


def test_reasoning_text_stays_out_of_the_answer(
    _settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The extractors read ``reply.text``; ``reasoning_content`` must not reach it."""
    _wire(monkeypatch)
    reply: Any = llamacpp.build(_settings).complete("question")

    assert "thinking" not in reply.text
    assert llamacpp.read_reply(reply.raw).reasoning == "thinking about it"
