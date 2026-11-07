"""An unlisted llama.cpp model refuses a request, never the start of the app.

Change one-llamacpp-router, bug "upgraded install cannot start". An install that
keeps ``llamacpp_embed_model`` outside the shipped model list must still build
an Engine, so ``omrs web`` and the MCP server start and the Settings page opens
to fix the list. The refusal (``RouterRefused``, ``model-not-listed``) comes
when a request would be sent, and nothing is sent.

No real server runs: an ``httpx`` mock transport records each request.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL, SHIPPED_MODELS
from omrs.core.llamacpp_router import RouterRefused
from omrs.core.providers.embeddings import llamacpp as embeddings_llamacpp

ROUTER = "http://127.0.0.1:8080/v1"
#: The model name of the upgraded install in the bug report.
UNLISTED = "qwen3-embedding:0.6b"
EMBEDDING_REPLY = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.5, 0.5]}],
    "model": "m",
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
}


class Wire:
    """Answers every embedding request and records each one."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return httpx.Response(200, json=EMBEDDING_REPLY)

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
    return wire


@pytest.fixture
def make(effective_settings: Callable[..., Any]) -> Callable[..., Any]:
    """Return a factory of managed-router settings with the shipped list."""

    def _make(**overrides: Any) -> Any:
        fields: dict[str, Any] = {
            "llamacpp_router_url": ROUTER,
            "llamacpp_router_server": "managed",
            "llamacpp_models": dict(SHIPPED_MODELS),
            "llamacpp_embed_model": UNLISTED,
            "llamacpp_chat_model": CLASSIFY_MODEL,
        }
        fields.update(overrides)
        return effective_settings(**fields)

    return _make


# ── Building the embedder sends and refuses nothing ─────────────────────────────────────────


def test_building_the_embedder_with_an_unlisted_model_succeeds(
    wire: Wire, make: Callable[..., Any]
) -> None:
    embedder = embeddings_llamacpp.build(make())
    assert embedder.model_name == UNLISTED
    assert wire.seen == []


# ── The first request is refused, and nothing reaches the router ────────────────────────────

_SYNC_CALLS = {
    "text": lambda e: e.get_text_embedding("t"),
    "query": lambda e: e.get_query_embedding("q"),
    "batch": lambda e: e.get_text_embedding_batch(["a", "b"]),
}


@pytest.mark.parametrize("call", sorted(_SYNC_CALLS))
def test_the_first_embedding_request_is_refused_and_sends_nothing(
    wire: Wire, make: Callable[..., Any], call: str
) -> None:
    embedder = embeddings_llamacpp.build(make())
    with pytest.raises(RouterRefused) as refused:
        _SYNC_CALLS[call](embedder)
    assert refused.value.reason == "model-not-listed"
    assert refused.value.role == "embeddings"
    assert UNLISTED not in str(refused.value)
    assert wire.seen == []


def test_the_async_embedding_request_is_refused_and_sends_nothing(
    wire: Wire, make: Callable[..., Any]
) -> None:
    embedder = embeddings_llamacpp.build(make())

    async def run() -> None:
        await embedder.aget_text_embedding("t")

    with pytest.raises(RouterRefused) as refused:
        asyncio.run(run())
    assert refused.value.reason == "model-not-listed"
    assert wire.seen == []


def test_a_model_override_is_checked_at_the_request_too(
    wire: Wire, make: Callable[..., Any]
) -> None:
    embedder = embeddings_llamacpp.build(make(llamacpp_embed_model=EMBED_MODEL), model=UNLISTED)
    with pytest.raises(RouterRefused):
        embedder.get_text_embedding("t")
    assert wire.seen == []


def test_a_listed_model_still_sends_its_request(wire: Wire, make: Callable[..., Any]) -> None:
    embeddings_llamacpp.build(make(llamacpp_embed_model=EMBED_MODEL)).get_text_embedding("t")
    assert wire.last_body()["model"] == EMBED_MODEL


def test_external_mode_does_not_refuse_an_unlisted_name(
    wire: Wire, make: Callable[..., Any]
) -> None:
    settings = make(llamacpp_router_server="external", llamacpp_models={})
    embeddings_llamacpp.build(settings).get_text_embedding("t")
    assert wire.last_body()["model"] == UNLISTED


# ── An Engine builds with the same settings ─────────────────────────────────────────────────


def _write_repro_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the settings file at the bug report's ``omrs.jsonc``; drop the env that beats it."""
    folder = tmp_path / "repro-config"
    folder.mkdir()
    (folder / "omrs.jsonc").write_text(
        json.dumps({"embed_provider": "llamacpp", "llamacpp_embed_model": UNLISTED})
    )
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    for name in ("EMBED_PROVIDER", "LLAMACPP_EMBED_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_an_engine_builds_with_an_unlisted_embedding_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wire: Wire
) -> None:
    from omrs import compose

    _write_repro_config(monkeypatch, tmp_path)
    settings = compose.get_settings()
    assert settings.llamacpp_router_server == "managed"
    assert UNLISTED not in {entry.model for entry in settings.llamacpp_models.values()}

    engine = compose.build_engine()
    try:
        assert wire.seen == []
    finally:
        engine.close()
