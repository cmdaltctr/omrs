"""Classification and Chat stay apart on llama.cpp (ADR-108, design D3).

Both go to the one router address (one-llamacpp-router D2). An answer role never
falls back to the Text model (classification).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core.providers.llm import llamacpp
from omrs.core.settings import EffectiveSettings, MetadataBlock

ROUTER = "http://127.0.0.1:8080/v1"


def settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "llamacpp_router_url": ROUTER,
        "llamacpp_router_server": "external",
        "llamacpp_chat_model": "Qwen/Qwen3-0.6B-GGUF:Q8_0",
        "metadata": SimpleNamespace(classify_timeout=30.0),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
    llamacpp.build(settings())
    assert (recorded[0]["api_base"], recorded[0]["model"]) == (
        ROUTER,
        "Qwen/Qwen3-0.6B-GGUF:Q8_0",
    )


def test_an_answer_model_goes_to_the_router_address(recorded: list[dict[str, Any]]) -> None:
    llamacpp.build(settings(), answer_model="Qwen/Qwen3-4B-GGUF")
    assert (recorded[0]["api_base"], recorded[0]["model"]) == (ROUTER, "Qwen/Qwen3-4B-GGUF")


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_answer_model_is_refused_and_builds_nothing(
    recorded: list[dict[str, Any]], blank: str
) -> None:
    with pytest.raises(ValueError, match=r"Settings > Chat"):
        llamacpp.build(settings(), answer_model=blank)
    assert recorded == []


# ── The llamaindex classification path builds on the router address ─────


def _effective(**overrides: Any) -> EffectiveSettings:
    return EffectiveSettings(
        llamacpp_router_url=ROUTER,
        llamacpp_router_server="external",
        llamacpp_chat_model="Qwen/Qwen3-0.6B-GGUF:Q8_0",
        metadata=MetadataBlock(classify_max_attempts=1),
        **overrides,
    )


@pytest.mark.metadata_llm
def test_llamaindex_classification_builds_on_the_router_address(
    recorded: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.metadata import extractor, llamaindex

    async def local(*_: Any, **__: Any) -> dict[str, Any]:
        return {"category": "uncategorised", "keywords": [], "summary": ""}

    monkeypatch.setattr(extractor, "_dispatch_local_extraction", local)
    resolved = _effective(metadata_llm_provider="local", local_backend="llamacpp")
    asyncio.run(llamaindex._extract_llamaindex_async("text", "f.txt", resolved))
    assert recorded[0]["api_base"] == ROUTER
    assert recorded[0]["model"] == "Qwen/Qwen3-0.6B-GGUF:Q8_0"
