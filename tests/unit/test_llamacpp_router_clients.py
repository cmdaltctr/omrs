"""Every llama.cpp client sends its request to the router address with the entry's model name.

Change one-llamacpp-router, tasks 2.3 (provider side) and 2.6. The clients are the embedder,
the LLM that Chat, the judge and classification build, and the direct classification call.
No real server runs: an ``httpx`` mock transport records each request.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from omrs.config.llamacpp_models import (
    CLASSIFY_MODEL,
    EMBED_MODEL,
    SHIPPED_MODELS,
    LlamaCppModelEntry,
)
from omrs.core.llamacpp_router import RouterRefused
from omrs.core.metadata import llamacpp as metadata_llamacpp
from omrs.core.metadata._common import _degradation_flag
from omrs.core.providers.embeddings import llamacpp as embeddings_llamacpp
from omrs.core.providers.llm import llamacpp as llm_llamacpp

ROUTER = "http://127.0.0.1:8080/v1"
OTHER = "Other/Text-GGUF:Q8_0"

EMBEDDING_REPLY = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.5, 0.5]}],
    "model": "m",
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
}
CHAT_REPLY = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "m",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "A"}}
    ],
    "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
}
CLASSIFY_REPLY = {
    "choices": [{"message": {"content": '{"category": "ai", "keywords": ["k"], "summary": "s"}'}}]
}


class Wire:
    """Answers every request with the matching reply and records what was sent."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path = request.url.path
        if path.endswith("/embeddings"):
            return httpx.Response(200, json=EMBEDDING_REPLY)
        if path.endswith("/chat/completions"):
            return httpx.Response(200, json=CHAT_REPLY)
        return httpx.Response(404)

    def clients(self, role: str) -> dict[str, Any]:
        return {
            "http_client": httpx.Client(transport=self.transport),
            "async_http_client": httpx.AsyncClient(transport=self.transport),
        }

    def last_body(self) -> dict[str, Any]:
        return json.loads(self.seen[-1].content)


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Wire:
    wire = Wire()
    monkeypatch.setattr(embeddings_llamacpp, "http_clients", wire.clients)
    monkeypatch.setattr(llm_llamacpp, "http_clients", wire.clients)
    return wire


@pytest.fixture
def make(effective_settings: Callable[..., Any]) -> Callable[..., Any]:
    """Return a factory of settings with the shipped list, the router address and role models."""

    def _make(**overrides: Any) -> Any:
        fields: dict[str, Any] = {
            "llamacpp_router_url": ROUTER,
            "llamacpp_router_server": "managed",
            "llamacpp_models": dict(SHIPPED_MODELS),
            "llamacpp_embed_model": EMBED_MODEL,
            "llamacpp_chat_model": CLASSIFY_MODEL,
        }
        fields.update(overrides)
        return effective_settings(**fields)

    return _make


# ── A request goes to the router address with the model name ─────────────────────────────────


def test_the_embedder_posts_to_the_router_with_the_embedding_model(
    wire: Wire, make: Callable[..., Any]
) -> None:
    embedder = embeddings_llamacpp.build(make())
    embedder.get_text_embedding("some text")
    assert str(wire.seen[-1].url) == f"{ROUTER}/embeddings"
    assert wire.last_body()["model"] == EMBED_MODEL


def test_the_embedder_names_a_model_override(wire: Wire, make: Callable[..., Any]) -> None:
    other = LlamaCppModelEntry(
        model=OTHER, preset={"embeddings": True, "pooling": "mean", "ctx-size": 512}
    )
    settings = make(llamacpp_models={**SHIPPED_MODELS, "other": other})
    embeddings_llamacpp.build(settings, model=OTHER).get_text_embedding("t")
    assert wire.last_body()["model"] == OTHER


def test_chat_and_classification_post_to_the_router_with_their_own_model(
    wire: Wire, make: Callable[..., Any]
) -> None:
    chat_entry = LlamaCppModelEntry(model=OTHER, preset={"ctx-size": 8192})
    settings = make(llamacpp_models={**SHIPPED_MODELS, "chat": chat_entry})
    llm_llamacpp.build(settings, answer_model=OTHER).chat([_message("hi")])
    assert str(wire.seen[-1].url) == f"{ROUTER}/chat/completions"
    assert wire.last_body()["model"] == OTHER
    llm_llamacpp.build(settings).chat([_message("hi")])
    assert str(wire.seen[-1].url) == f"{ROUTER}/chat/completions"
    assert wire.last_body()["model"] == CLASSIFY_MODEL


def test_embeddings_and_chat_share_one_address(wire: Wire, make: Callable[..., Any]) -> None:
    chat_entry = LlamaCppModelEntry(model=OTHER, preset={})
    settings = make(llamacpp_models={**SHIPPED_MODELS, "chat": chat_entry})
    embeddings_llamacpp.build(settings).get_text_embedding("t")
    llm_llamacpp.build(settings, answer_model=OTHER).chat([_message("hi")])
    assert all(str(request.url).startswith(f"{ROUTER}/") for request in wire.seen)
    assert {request.url.netloc.decode() for request in wire.seen} == {"127.0.0.1:8080"}
    assert [json.loads(r.content)["model"] for r in wire.seen] == [EMBED_MODEL, OTHER]


def _message(text: str) -> Any:
    from llama_index.core.llms import ChatMessage

    return ChatMessage(role="user", content=text)


class _ClassifyClient:
    """Stands in for ``httpx.AsyncClient`` on the direct classification call."""

    sent: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _ClassifyClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        _ClassifyClient.sent.append((url, kwargs["json"]))
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=CLASSIFY_REPLY, request=request)


def _classify(settings: Any) -> tuple[dict[str, Any], bool]:
    async def run() -> tuple[dict[str, Any], bool]:
        token = _degradation_flag.set(False)
        try:
            result = await metadata_llamacpp._extract_llamacpp_chat_async("text", "f.txt", settings)
            return result, _degradation_flag.get()
        finally:
            _degradation_flag.reset(token)

    return asyncio.run(run())


@pytest.fixture
def classify_wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    _ClassifyClient.sent = []
    monkeypatch.setattr("httpx.AsyncClient", _ClassifyClient)
    return _ClassifyClient.sent


def test_direct_classification_posts_to_the_router_with_the_text_model(
    classify_wire: list[tuple[str, dict[str, Any]]], make: Callable[..., Any]
) -> None:
    result, degraded = _classify(make())
    assert result["category"] == "ai" and degraded is False
    assert classify_wire[0][0] == f"{ROUTER}/chat/completions"
    assert classify_wire[0][1]["model"] == CLASSIFY_MODEL


# ── Managed mode refuses before any contact ─────────────────────────────────────────────────


def test_an_unlisted_embedding_model_is_refused_before_contact(
    wire: Wire, make: Callable[..., Any]
) -> None:
    embedder = embeddings_llamacpp.build(make(llamacpp_embed_model=OTHER))  # building never refuses
    with pytest.raises(RouterRefused) as refused:
        embedder.get_text_embedding("t")
    assert refused.value.reason == "model-not-listed"
    assert wire.seen == []


def test_an_unlisted_chat_model_is_refused_before_contact(
    wire: Wire, make: Callable[..., Any]
) -> None:
    with pytest.raises(RouterRefused) as refused:
        llm_llamacpp.build(make(), answer_model=OTHER)
    assert refused.value.reason == "model-not-listed"
    assert wire.seen == []


def test_an_unlisted_classification_model_is_refused_before_contact(
    wire: Wire, make: Callable[..., Any]
) -> None:
    with pytest.raises(RouterRefused) as refused:
        llm_llamacpp.build(make(llamacpp_chat_model=OTHER))
    assert refused.value.reason == "model-not-listed"
    assert wire.seen == []


def test_an_embedding_entry_cannot_serve_chat_or_classification(
    wire: Wire, make: Callable[..., Any]
) -> None:
    with pytest.raises(RouterRefused) as chat:
        llm_llamacpp.build(make(), answer_model=EMBED_MODEL)
    with pytest.raises(RouterRefused) as classification:
        llm_llamacpp.build(make(llamacpp_chat_model=EMBED_MODEL))
    assert chat.value.reason == classification.value.reason == "role-mismatch"
    assert wire.seen == []


def test_an_unlisted_classification_call_sends_nothing_and_degrades(
    classify_wire: list[tuple[str, dict[str, Any]]], make: Callable[..., Any]
) -> None:
    result, degraded = _classify(make(llamacpp_chat_model=OTHER))
    assert result["category"] == "uncategorised"
    assert degraded is True
    assert classify_wire == []


# ── External mode does not check the name ───────────────────────────────────────────────────


def test_external_mode_sends_any_model_name_to_the_address(
    wire: Wire,
    classify_wire: list[tuple[str, dict[str, Any]]],
    make: Callable[..., Any],
) -> None:
    settings = make(
        llamacpp_router_server="external",
        llamacpp_router_url="http://127.0.0.1:9931/v1",
        llamacpp_models={},
        llamacpp_embed_model="any-embedding",
        llamacpp_chat_model="any-text",
    )
    embeddings_llamacpp.build(settings).get_text_embedding("t")
    assert str(wire.seen[-1].url) == "http://127.0.0.1:9931/v1/embeddings"
    assert wire.last_body()["model"] == "any-embedding"
    llm_llamacpp.build(settings, answer_model="any-chat").chat([_message("hi")])
    assert wire.last_body()["model"] == "any-chat"
    _classify(settings)
    assert classify_wire[0] == (
        "http://127.0.0.1:9931/v1/chat/completions",
        classify_wire[0][1],
    )
    assert classify_wire[0][1]["model"] == "any-text"


# ── Chat and the judge build only from an explicit name ─────────────────────────────────────


@pytest.mark.parametrize("name", ["", "   "])
def test_an_empty_chat_or_judge_name_is_never_replaced_by_the_text_model(
    make: Callable[..., Any], name: str
) -> None:
    with pytest.raises(ValueError, match="Choose a model for llama.cpp") as raised:
        llm_llamacpp.build(make(), answer_model=name)
    assert not isinstance(raised.value, RouterRefused)
