"""llama.cpp embedding provider.

Constructs an ``OpenAILikeEmbedding`` for a llama.cpp server's OpenAI-compatible
``/v1`` endpoint. This accepts arbitrary local model identifiers and requires
``llama-index-embeddings-openai-like``.

The embedder sends text unchanged. LlamaIndex's OpenAI helpers replace every
line break with a space, which Ollama does not do. With the same model, that
gives different vectors for the same chunk (cosine down to 0.86 on Markdown)
and drops the chunk's line structure.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....config import Settings


@cache
def _verbatim_embedding_class(base: type) -> type:
    """Return a subclass of *base* (``OpenAILikeEmbedding``) that keeps line breaks.

    Cached by base class, so the import in :func:`build` still runs on every
    call and still raises when the package is missing.
    """

    class VerbatimOpenAILikeEmbedding(base):  # type: ignore[valid-type,misc]
        """Posts each input to ``/embeddings`` as it is, with the parent's retries."""

        def _embed(self, texts: list[str]) -> list[list[float]]:
            client = self._get_client()

            @self._create_retry_decorator()
            def call() -> list[list[float]]:
                answer = client.embeddings.create(
                    input=texts, model=self.model_name, **self.additional_kwargs
                )
                return [item.embedding for item in answer.data]

            return call()

        async def _aembed(self, texts: list[str]) -> list[list[float]]:
            aclient = self._get_aclient()

            @self._create_retry_decorator()
            async def call() -> list[list[float]]:
                answer = await aclient.embeddings.create(
                    input=texts, model=self.model_name, **self.additional_kwargs
                )
                return [item.embedding for item in answer.data]

            return await call()

        def _get_query_embedding(self, query: str) -> list[float]:
            return self._embed([query])[0]

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return (await self._aembed([query]))[0]

        def _get_text_embedding(self, text: str) -> list[float]:
            return self._embed([text])[0]

        async def _aget_text_embedding(self, text: str) -> list[float]:
            return (await self._aembed([text]))[0]

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._embed(texts)

        async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return await self._aembed(texts)

    return VerbatimOpenAILikeEmbedding


def build(settings: Settings, *, model: str | None = None) -> Any:
    """Construct the llama.cpp embedder from *settings*.

    Args:
        settings: Resolved settings (URL and batch size).
        model: Optional model name that replaces ``llamacpp_embed_model``.

    Raises:
        ImportError: If ``llama-index-embeddings-openai-like`` is absent.
    """
    try:
        from llama_index.embeddings.openai_like import OpenAILikeEmbedding
    except ImportError:
        raise ImportError(
            "Provider 'llamacpp' requires llama-index-embeddings-openai-like. "
            "Install it with: uv sync --extra llamacpp"
        ) from None

    return _verbatim_embedding_class(OpenAILikeEmbedding)(
        model_name=model or settings.llamacpp_embed_model,
        api_base=settings.llamacpp_embed_url,
        api_key="no-key",
        embed_batch_size=settings.ingestion.embed_batch_size,
    )
