"""Chat, classification and embedding clients on the one router (one-llamacpp-router, task 3.7).

``compose`` installs a gate resolver; the llama.cpp clients in ``core/`` ask it
for a gate and send every request through it, naming their model. A managed
router starts the fake router (``tests/fixtures/llamacpp``) as a client; an
external router starts nothing. Another OMRS process adopts the same router.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import pid_alive
from tests.unit.test_llamacpp_router_compose_support import (
    CHAT,
    EMBED,
    RouterRig,
    composed_rig,
    point_at,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _chat_on_router(rig: RouterRig, monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    """Point the settings at the fake router with Chat on llama.cpp (the shared 4B entry)."""
    point_at(
        rig,
        monkeypatch,
        ANSWER__ENABLED="true",
        ANSWER__PROVIDER="llamacpp",
        ANSWER__MODEL=CHAT,
        **extra,
    )


def _chat_text(llm: Any) -> str:
    from llama_index.core.llms import ChatMessage

    return str(llm.chat([ChatMessage(role="user", content="hi")]).message.content)


def _router_pid(rig: RouterRig) -> int:
    return int((rig.folder / "starts.txt").read_text(encoding="utf-8").split()[0])


# ── Chat ─────────────────────────────────────────────────────────────────


def test_a_cli_chat_answer_starts_the_managed_router_as_a_client(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose

    rig.set_env(FAKE_LLAMA_CONTENT="the fake answer")
    _chat_on_router(rig, monkeypatch)
    compose.ensure_runtime_setup()  # the CLI entry point composes the process

    assert _chat_text(compose.build_answer_llm()) == "the fake answer"

    assert rig.starts() == 1
    other = rig.worker()  # a second OMRS process adopts the same router
    assert other.call("request", model=CHAT)["ok"] is True
    assert rig.starts() == 1


def test_an_external_router_starts_nothing(rig: RouterRig, monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs import compose
    from omrs.core import runtime_gate

    _chat_on_router(rig, monkeypatch, LLAMACPP_ROUTER_SERVER="external")
    compose.ensure_runtime_setup()

    assert runtime_gate.gate_for("chat") is None
    with pytest.raises(Exception):  # noqa: B017 - nothing listens on the port
        _chat_text(compose.build_answer_llm())
    assert rig.starts() == 0


def test_a_refused_start_is_one_plain_answer_with_no_retry(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is an answer the OpenAI client must not retry, so the start runs once."""
    from omrs import compose

    rig.set_env(FAKE_LLAMA_EARLY_EXIT=rig.folder / "early-exits")
    _chat_on_router(rig, monkeypatch)
    compose.ensure_runtime_setup()

    with pytest.raises(Exception, match="stopped before it was ready"):
        _chat_text(compose.build_answer_llm())
    assert (rig.folder / "early-exits").read_text(encoding="utf-8").strip() == "1"


# ── Classification ───────────────────────────────────────────────────────


@pytest.mark.metadata_llm
def test_a_refused_classification_is_not_retried(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """Each try would start the router again, so a refusal ends the attempts at once."""
    from omrs import compose, compose_runtimes
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    rig.set_env(FAKE_LLAMA_EARLY_EXIT=rig.folder / "early-exits")
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    settings = effective_settings(
        llamacpp_router_url=f"http://127.0.0.1:{rig.port}/v1",
        llamacpp_chat_model=CHAT,
        llamacpp_models=dict(compose.get_settings().llamacpp_models),
        classify_max_attempts=3,
    )

    result = asyncio.run(_extract_llamacpp_chat_async("some text", settings=settings))

    assert result["category"] == "uncategorised"
    assert (rig.folder / "early-exits").read_text(encoding="utf-8").strip() == "1"


def test_classification_and_chat_share_one_router(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.core.providers.llm import llamacpp

    rig.set_env(FAKE_LLAMA_CONTENT="classified")
    _chat_on_router(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    llm = llamacpp.build(compose.get_settings())  # no answer model: the classification role

    assert _chat_text(llm) == "classified"
    assert _chat_text(compose.build_answer_llm()) == "classified"
    assert rig.starts() == 1


def test_every_role_gets_the_router_gate_while_managed(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.compose_runtimes import RouterGate

    _chat_on_router(rig, monkeypatch)

    for role in ("embeddings", "classification", "chat"):
        assert isinstance(compose_runtimes.gate(role, compose.get_settings()), RouterGate)


# ── Embeddings ───────────────────────────────────────────────────────────


def _embedder() -> Any:
    from omrs import compose
    from omrs.core.providers.embeddings import llamacpp

    return llamacpp.build(compose.get_settings())


def test_managed_embeddings_start_the_router_and_embed_text(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.llamacpp.fake_llama_server import EMBEDDING_VECTOR

    from omrs import compose_runtimes

    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    vector = _embedder().get_text_embedding("hello")

    assert vector == pytest.approx(EMBEDDING_VECTOR)
    assert rig.starts() == 1
    assert pid_alive(_router_pid(rig))


def test_embeddings_and_chat_run_on_one_router_folder(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes

    _chat_on_router(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    _embedder().get_text_embedding("hello")
    _chat_text(compose.build_answer_llm())

    assert rig.starts() == 1
    folders = sorted(
        p.name for p in (compose_runtimes.runtime_manager().root / "runtimes").iterdir()
    )
    assert folders == ["router"]


def test_a_client_process_keeps_the_router_after_this_process_leaves(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes

    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)
    _embedder().get_text_embedding("hello")
    other = rig.worker()
    assert other.call("request", model=EMBED, path="/v1/embeddings")["ok"] is True

    compose_runtimes.reset()  # this process leaves

    assert pid_alive(_router_pid(rig))
    assert rig.starts() == 1
