"""Chat, classification and embedding clients on the shared runtime (tasks 5.2 and 5.3).

``compose`` installs a gate resolver; the llama.cpp clients in ``core/`` ask
it for a gate and send every request through it. A managed role starts the
fake ``llama-server`` as a client; an external role starts nothing.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import (
    ClientProcess,
    RuntimeEnv,
    pid_alive,
    runtime_env_fixture,
)
from tests.unit.llamacpp_fake import free_port

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    from omrs import compose_runtimes

    yield from runtime_env_fixture(tmp_path, monkeypatch)
    compose_runtimes.reset()


def _managed_chat(env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch, **extra: str) -> Any:
    """Point the settings at the fake as OMRS's own Chat server; return the fake."""
    fake = env.fake()
    port = free_port()
    values = {
        "LLAMACPP_SERVER_BINARY": str(fake.binary),
        "LLAMACPP_CHAT_SERVER": "managed",
        "LLAMACPP_CHAT_URL": f"http://127.0.0.1:{port}/v1",
        "LLAMACPP_CONTEXT_WINDOW": "2048",
        "ANSWER__ENABLED": "true",
        "ANSWER__PROVIDER": "llamacpp",
        "ANSWER__MODEL": str(fake.model),
        **extra,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    fake.port = port
    return fake


def _chat_text(llm: Any) -> str:
    from llama_index.core.llms import ChatMessage

    return str(llm.chat([ChatMessage(role="user", content="hi")]).message.content)


# ── 5.2 Chat ─────────────────────────────────────────────────────────────


def test_a_cli_chat_answer_starts_the_managed_server_as_a_client(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose

    fake = _managed_chat(runtime_env, monkeypatch)
    fake.set_env(FAKE_LLAMA_CONTENT="the fake answer")
    compose.ensure_runtime_setup()  # the CLI entry point composes the process

    assert _chat_text(compose.build_answer_llm()) == "the fake answer"

    starts = fake.starts()
    assert len(starts) == 1
    assert starts[0]["argv"][-2:] == ["-c", "2048"]
    other = runtime_env.client()  # a second OMRS process adopts the same server
    assert other.join(fake.chat(fake.port))["ok"] is True
    assert other.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_an_external_chat_server_starts_nothing(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose
    from omrs.core import runtime_gate

    fake = _managed_chat(runtime_env, monkeypatch, LLAMACPP_CHAT_SERVER="external")
    compose.ensure_runtime_setup()

    assert runtime_gate.gate_for("chat") is None
    with pytest.raises(Exception):  # noqa: B017 - nothing listens on the port
        _chat_text(compose.build_answer_llm())
    assert fake.starts() == []


def test_a_refused_start_is_one_plain_answer_with_no_retry(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is a 503 the OpenAI client must not retry, so the start runs once."""
    from omrs import compose

    fake = _managed_chat(runtime_env, monkeypatch)
    fake.set_env(FAKE_LLAMA_EARLY_EXIT=str(runtime_env.folder / "early-exits"))
    compose.ensure_runtime_setup()

    with pytest.raises(Exception, match="stopped before it was ready"):
        _chat_text(compose.build_answer_llm())
    assert (runtime_env.folder / "early-exits").read_text(encoding="utf-8").strip() == "1"


# ── 5.2 Classification ───────────────────────────────────────────────────


@pytest.mark.metadata_llm
def test_classification_uses_the_chat_runtime_when_its_address_is_blank(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    from omrs import compose_runtimes
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    fake = _managed_chat(runtime_env, monkeypatch)
    fake.set_env(FAKE_LLAMA_CONTENT='{"category": "fake-category", "keywords": ["k"]}')
    compose_runtimes.install_gates(None)
    settings = effective_settings(llamacpp_chat_url=f"http://127.0.0.1:{fake.port}/v1")

    result = asyncio.run(_extract_llamacpp_chat_async("some text", settings=settings))

    assert result["category"] == "fake-category"
    assert len(fake.starts()) == 1


@pytest.mark.metadata_llm
def test_classification_with_its_own_address_starts_nothing(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    from omrs import compose_runtimes
    from omrs.core import runtime_gate
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    own = f"http://127.0.0.1:{free_port()}/v1"
    fake = _managed_chat(runtime_env, monkeypatch, LLAMACPP_CLASSIFY_URL=own)
    compose_runtimes.install_gates(None)
    settings = effective_settings(
        llamacpp_chat_url=f"http://127.0.0.1:{fake.port}/v1", llamacpp_classify_url=own
    )

    assert runtime_gate.gate_for("classification") is None
    result = asyncio.run(_extract_llamacpp_chat_async("some text", settings=settings))

    assert result["category"] == "uncategorised"  # nothing listens at its own address
    assert fake.starts() == []


@pytest.mark.metadata_llm
def test_a_refused_classification_is_not_retried(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """Each try would start the server again, so a refusal ends the attempts at once."""
    from omrs import compose_runtimes
    from omrs.core.metadata.llamacpp import _extract_llamacpp_chat_async

    fake = _managed_chat(runtime_env, monkeypatch)
    fake.set_env(FAKE_LLAMA_EARLY_EXIT=str(runtime_env.folder / "early-exits"))
    compose_runtimes.install_gates(None)
    settings = effective_settings(
        llamacpp_chat_url=f"http://127.0.0.1:{fake.port}/v1", classify_max_attempts=3
    )

    result = asyncio.run(_extract_llamacpp_chat_async("some text", settings=settings))

    assert result["category"] == "uncategorised"
    assert (runtime_env.folder / "early-exits").read_text(encoding="utf-8").strip() == "1"


def test_the_classification_llm_shares_the_chat_server(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes
    from omrs.core.providers.llm import llamacpp

    fake = _managed_chat(runtime_env, monkeypatch)
    fake.set_env(FAKE_LLAMA_CONTENT="classified")
    compose_runtimes.install_gates(None)

    llm = llamacpp.build(compose.get_settings())  # no answer model: the classification role

    assert _chat_text(llm) == "classified"
    assert _chat_text(compose.build_answer_llm()) == "classified"
    assert len(fake.starts()) == 1


# ── 5.3 Embeddings ───────────────────────────────────────────────────────


def _embed_settings(env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch, mode: str | None) -> Any:
    fake = env.fake()
    port = free_port()
    monkeypatch.setenv("LLAMACPP_SERVER_BINARY", str(fake.binary))
    monkeypatch.setenv("LLAMACPP_EMBED_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", str(fake.model))
    if mode is not None:
        monkeypatch.setenv("LLAMACPP_EMBED_SERVER", mode)
    fake.port = port
    return fake


def _embedder() -> Any:
    from omrs import compose
    from omrs.core.providers.embeddings import llamacpp

    return llamacpp.build(compose.get_settings())


def test_default_external_embeddings_start_nothing(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes
    from omrs.core import runtime_gate

    fake = _embed_settings(runtime_env, monkeypatch, mode=None)
    compose_runtimes.install_gates(None)

    assert runtime_gate.gate_for("embeddings") is None
    embedder = _embedder()
    embedder.max_retries = 0
    with pytest.raises(Exception):  # noqa: B017 - nothing listens on the port
        embedder.get_text_embedding("hello")
    assert fake.starts() == []


def test_managed_embeddings_start_the_fake_with_embedding_and_embed_text(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.llamacpp.fake_llama_server import EMBEDDING_VECTOR

    from omrs import compose_runtimes

    fake = _embed_settings(runtime_env, monkeypatch, mode="managed")
    compose_runtimes.install_gates(None)

    vector = _embedder().get_text_embedding("hello")

    assert vector == pytest.approx(EMBEDDING_VECTOR)
    (start,) = fake.starts()
    assert start["argv"][-3:] == ["--port", str(fake.port), "--embedding"]
    assert pid_alive(int(start["pid"]))


def test_managed_embeddings_and_chat_are_two_runtimes(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes

    chat = _managed_chat(runtime_env, monkeypatch)
    monkeypatch.setenv("LLAMACPP_EMBED_SERVER", "managed")
    monkeypatch.setenv("LLAMACPP_EMBED_URL", f"http://127.0.0.1:{free_port()}/v1")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", str(chat.model))
    compose_runtimes.install_gates(None)

    _embedder().get_text_embedding("hello")
    _chat_text(compose.build_answer_llm())

    assert sorted("--embedding" in s["argv"] for s in chat.starts()) == [False, True]
    folders = sorted(
        p.name for p in (compose_runtimes.runtime_manager().root / "runtimes").iterdir()
    )
    assert folders == ["chat", "embeddings"]


def test_a_client_process_keeps_the_embedding_server_after_this_process_leaves(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose_runtimes
    from omrs.integrations.llamacpp_runtime.spec import embeddings_spec

    fake = _embed_settings(runtime_env, monkeypatch, mode="managed")
    compose_runtimes.install_gates(None)
    _embedder().get_text_embedding("hello")
    other: ClientProcess = runtime_env.client()
    spec = embeddings_spec(
        mode="managed", binary=str(fake.binary), model=str(fake.model), port=fake.port
    )
    assert other.join(spec)["ok"] is True

    compose_runtimes.reset()  # this process leaves

    assert pid_alive(int(fake.starts()[0]["pid"]))
    assert len(fake.starts()) == 1
