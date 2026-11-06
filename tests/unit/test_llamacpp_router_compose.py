"""Compose wires every llama.cpp client to the one router (one-llamacpp-router, task 3.7).

``compose_runtimes.install_gates`` installs one resolver. Every role gets a gate
in front of the router: it takes the router lease, makes the request's model
ready, and takes the model's request lock when the entry is one-slot. An
external router gets no gate. Requests go to the fake router of
``tests/fixtures/llamacpp``; no real ``llama-server`` starts.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.unit.test_llamacpp_router_compose_support import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    composed_rig,
    point_at,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _requests(rig: RouterRig) -> list[dict[str, Any]]:
    path = rig.folder / "requests.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _embed(text: str) -> list[float]:
    from omrs import compose
    from omrs.core.providers.embeddings import llamacpp

    embedder = llamacpp.build(compose.get_settings())
    embedder.max_retries = 0
    return list(embedder.get_text_embedding(text))


def _chat(model: str) -> str:
    from llama_index.core.llms import ChatMessage

    from omrs import compose
    from omrs.core.providers.llm import llamacpp

    llm = llamacpp.build(compose.get_settings(), answer_model=model)
    return str(llm.chat([ChatMessage(role="user", content="hi")]).message.content)


# ── One router, every role ────────────────────────────────────────────────


def test_embeddings_and_chat_share_one_router_each_with_its_model_name(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec llamacpp-router "Embeddings and Chat share one address"."""
    from tests.fixtures.llamacpp.fake_llama_server import EMBEDDING_VECTOR

    from omrs import compose_runtimes

    rig.set_env(
        FAKE_LLAMA_CONTENT="the fake answer", FAKE_LLAMA_REQUESTS=rig.folder / "requests.jsonl"
    )
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    assert _embed("hello") == pytest.approx(EMBEDDING_VECTOR)
    assert _chat(CHAT) == "the fake answer"

    assert rig.starts() == 1
    assert [body["model"] for body in _requests(rig)] == [EMBED, CHAT]


@pytest.mark.metadata_llm
def test_classification_goes_to_the_router_with_its_model(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    rig.set_env(
        FAKE_LLAMA_CONTENT='{"category": "fake-category", "keywords": ["k"]}',
        FAKE_LLAMA_REQUESTS=rig.folder / "requests.jsonl",
    )
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    settings = effective_settings(
        llamacpp_router_url=f"http://127.0.0.1:{rig.port}/v1",
        llamacpp_chat_model=CHAT,
        llamacpp_models=dict(compose.get_settings().llamacpp_models),
    )

    result = asyncio.run(_extract_llamacpp_chat_async("some text", settings=settings))

    assert result["category"] == "fake-category"
    assert [body["model"] for body in _requests(rig)] == [CHAT]
    assert rig.starts() == 1


def test_the_gate_makes_the_model_ready_before_its_request(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "A model is made ready before its request is timed": load first, then send."""
    from omrs import compose_runtimes
    from omrs.integrations.llamacpp_runtime import readiness

    calls: list[str] = []
    real = readiness.ensure_loaded

    def spy(url: str, model: str) -> None:
        calls.append(model)
        real(url, model)

    monkeypatch.setattr(readiness, "ensure_loaded", spy)
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    _embed("hello")

    assert calls == [EMBED]


def test_a_one_slot_model_takes_its_own_request_lock(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "One-slot models wait on their own request lock": the lock of that model only."""
    from omrs import compose_runtimes
    from omrs.integrations.llamacpp_runtime import router_lease

    taken: list[str] = []
    real = router_lease.request_lock

    def spy(root: Path, model: str) -> Any:
        taken.append(model)
        return real(root, model)

    monkeypatch.setattr(router_lease, "request_lock", spy)
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    _embed("hello")  # the embedding entry is one-slot (parallel 1)
    _chat(CHAT)  # the Chat entry has two slots

    assert taken == [EMBED]


# ── Modes and refusals ───────────────────────────────────────────────────


def test_an_external_router_gets_no_gate_and_starts_nothing(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec llamacpp-runtimes "External embeddings start nothing"."""
    from omrs import compose_runtimes
    from omrs.core import runtime_gate

    point_at(rig, monkeypatch, LLAMACPP_ROUTER_SERVER="external")
    compose_runtimes.install_gates(None)

    for role in ("embeddings", "classification", "chat"):
        assert runtime_gate.gate_for(role) is None
    with pytest.raises(Exception):  # noqa: B017 - nothing listens on the port
        _embed("hello")
    assert rig.starts() == 0


def test_a_managed_router_with_no_program_is_one_plain_refusal(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No program and none provisioned: ``not-configured``, nothing starts, no retry."""
    from omrs import compose_runtimes
    from omrs.core import runtime_gate

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "no-provisioned-build"))
    point_at(rig, monkeypatch, LLAMACPP_SERVER_BINARY="")
    compose_runtimes.install_gates(None)

    gate = runtime_gate.gate_for("embeddings")
    request = httpx.Request("POST", "http://x/v1/embeddings", json={"model": EMBED})
    response = runtime_gate.GatedTransport(gate).handle_request(request)

    assert response.status_code == runtime_gate.REFUSED_STATUS
    assert response.headers[runtime_gate.NO_RETRY_HEADER] == "false"
    assert response.json()["error"]["code"] == "not-configured"
    assert rig.starts() == 0


def test_a_remote_address_for_a_managed_router_is_not_loopback(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.compose_runtimes import RefusedGate

    point_at(rig, monkeypatch, LLAMACPP_ROUTER_URL="http://10.0.0.5:8080/v1")

    gate = compose_runtimes.gate("chat", compose.get_settings())

    assert isinstance(gate, RefusedGate)
    assert gate.reason == "not-loopback"


def test_a_request_without_a_model_name_is_refused_before_any_contact(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes
    from omrs.core import runtime_gate

    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    request = httpx.Request("POST", "http://x/v1/embeddings", json={"input": "hello"})

    response = runtime_gate.GatedTransport(runtime_gate.gate_for("embeddings")).handle_request(
        request
    )

    assert response.json()["error"]["code"] == "model-not-listed"
    assert rig.starts() == 0


def test_a_listed_model_that_fails_to_load_does_not_stop_the_others(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "Load failure isolated", seen through the gate: a plain refusal for that model."""
    from omrs import compose_runtimes

    rig.set_env(FAKE_LLAMA_LOAD_FAIL=CLEF)
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    with pytest.raises(Exception, match="could not load the model"):
        _chat(CLEF)
    assert _embed("hello")


def test_the_async_gate_sends_through_the_router(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes
    from omrs.core import runtime_gate

    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    transport = runtime_gate.AsyncGatedTransport(runtime_gate.gate_for("embeddings"))

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.post(
                f"http://127.0.0.1:{rig.port}/v1/embeddings",
                json={"model": EMBED, "input": "hello"},
            )

    response = asyncio.run(send())

    assert response.status_code == 200
    assert response.json()["model"] == EMBED
