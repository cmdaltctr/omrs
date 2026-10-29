"""Contract: the llama.cpp embedder sends text to the server unchanged.

LlamaIndex's OpenAI embedding helpers replace every line break with a space.
Ollama keeps them, so the same model gives different vectors for the same
chunk, and Markdown structure is lost. Stored Ollama vectors of
Qwen3-Embedding-0.6B match llama.cpp only when the text is sent as it is.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.config import Settings
from omrs.core.ingestion.settings import IngestionSettings
from omrs.core.providers.embeddings import llamacpp

TEXT = "# Title\n\nFirst line.\nSecond line."
OTHER = "a\nb"


class _Embeddings:
    def __init__(self, calls: list[list[str]]) -> None:
        self.calls = calls

    def _answer(self, inputs: list[str]) -> Any:
        self.calls.append(list(inputs))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(i)]) for i, _ in enumerate(inputs)]
        )

    def create(self, *, input: list[str], model: str, **_: Any) -> Any:  # noqa: A002
        return self._answer(input)


class _AsyncEmbeddings(_Embeddings):
    async def create(self, *, input: list[str], model: str, **_: Any) -> Any:  # noqa: A002
        return self._answer(input)


@pytest.fixture
def embedder_and_calls(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[list[str]]]:
    settings = Settings(
        llamacpp_embed_model="Qwen3-Embedding-0.6B-Q8_0.gguf",
        llamacpp_embed_url="http://llama.example:8080/v1",
        ingestion=IngestionSettings(embed_batch_size=8),
    )
    embedder = llamacpp.build(settings)
    calls: list[list[str]] = []
    client = SimpleNamespace(embeddings=_Embeddings(calls))
    aclient = SimpleNamespace(embeddings=_AsyncEmbeddings(calls))
    monkeypatch.setattr(type(embedder), "_get_client", lambda self: client)
    monkeypatch.setattr(type(embedder), "_get_aclient", lambda self: aclient)
    return embedder, calls


def test_text_and_query_embeddings_keep_line_breaks(
    embedder_and_calls: tuple[Any, list[list[str]]],
) -> None:
    embedder, calls = embedder_and_calls
    embedder.get_text_embedding(TEXT)
    embedder.get_query_embedding(TEXT)
    embedder.get_text_embedding_batch([TEXT, OTHER])
    assert calls == [[TEXT], [TEXT], [TEXT, OTHER]]


def test_async_embeddings_keep_line_breaks(embedder_and_calls: tuple[Any, list[list[str]]]) -> None:
    embedder, calls = embedder_and_calls

    async def run() -> None:
        await embedder.aget_text_embedding(TEXT)
        await embedder.aget_query_embedding(TEXT)
        await embedder.aget_text_embedding_batch([TEXT, OTHER])

    asyncio.run(run())
    assert calls == [[TEXT], [TEXT], [TEXT, OTHER]]


def test_embedder_keeps_model_url_and_batch_size(
    embedder_and_calls: tuple[Any, list[list[str]]],
) -> None:
    embedder, _ = embedder_and_calls
    assert embedder.model_name == "Qwen3-Embedding-0.6B-Q8_0.gguf"
    assert embedder.api_base == "http://llama.example:8080/v1"
    assert embedder.embed_batch_size == 8
