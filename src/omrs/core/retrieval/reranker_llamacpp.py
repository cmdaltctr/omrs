"""Reranker backend that scores through the llama.cpp router (design D27).

One ``POST {router}/v1/rerank`` per query carries the model name, the query
and the candidate texts in input order. The router model is a Qwen3-Reranker
GGUF entry whose preset sets ``embeddings: true`` and ``pooling: rank``.

Score: for Qwen3 in rank pooling, llama.cpp applies a softmax to the
classifier output, and ``send_rerank`` returns its first value with no further
transform. So ``relevance_score`` is already a probability in [0, 1], and this
backend keeps it unchanged. A zero (float underflow) becomes the smallest
positive float, so every score is in (0, 1]. A score outside [0, 1] means a
different server build; the reply is refused, never mixed in. The pod check
(task 9.2 step 2a) confirms this on the real files.

An unreachable router, an HTTP error, an unknown model or a bad reply returns
the inputs un-reranked with ``_reranked`` false and a ``last_failure_reason``.
The backend never raises from ``rerank``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from .runtime_status import CacheProbe, RerankerRuntimeStatus

logger = logging.getLogger(__name__)

#: Seconds for one rerank call. Rerank mode can be slow on llama.cpp (issue
#: #30422), and a pool of 100 long chunks on the 8B model takes a while.
_TIMEOUT_SECONDS = 600.0

#: Seconds for the model-list read of the Settings runtime page. It matches the
#: page's router probe, so a router that does not answer cannot hold the page.
_LIST_TIMEOUT_SECONDS = 1.0

#: Characters of an HTTP error reply kept in the failure reason, so it stays one bounded line.
_ERROR_BODY_CHARS = 500


class LlamaCppReranker:
    """Rerank candidates through the router's ``/v1/rerank`` endpoint.

    Attributes:
        model_id: The router model name (``retrieval.rerank_model``).
        router_url: The router address (``llamacpp_router_url``, ends in ``/v1``).
        last_failure_reason: Why the last call returned un-reranked rows, or ``None``.
    """

    backend_name: str = "llamacpp"

    def __init__(self, model_id: str, router_url: str) -> None:
        """Initialise the backend with the router model name and address."""
        self.model_id = model_id
        self.router_url = router_url
        self.last_failure_reason: str | None = None

    @classmethod
    def from_settings(cls, settings: Any) -> LlamaCppReranker:
        """Build the backend from ``retrieval.rerank_model`` and ``llamacpp_router_url``."""
        return cls(
            model_id=settings.retrieval.rerank_model, router_url=settings.llamacpp_router_url
        )

    @classmethod
    def runtime_status(cls, settings: Any, cached: CacheProbe) -> RerankerRuntimeStatus:
        """Report whether the router lists the configured rerank model.

        One ``GET {router}/models`` with a 1 second timeout. A router that
        does not answer, or answers with an error, gives ``unknown``, because
        the model may be listed once the router runs.

        Args:
            settings: Effective settings (``retrieval.rerank_model`` and ``llamacpp_router_url``).
            cached: The Hugging Face cache probe. Not used: the router owns the files.
        """
        # Lazy: the runtime package imports its process manager on load.
        from ...integrations.llamacpp_runtime.model_list import served_model_names

        model = settings.retrieval.rerank_model.strip()
        try:
            response = httpx.get(
                f"{settings.llamacpp_router_url.rstrip('/')}/models", timeout=_LIST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            listed = set(served_model_names(response.json()))
        except (httpx.HTTPError, ValueError):
            return RerankerRuntimeStatus(
                "unknown", "The llama.cpp router did not answer, so its model list is not known."
            )
        if model in listed:
            return RerankerRuntimeStatus("ready")
        reason = (
            f"The llama.cpp router does not list {model}. Add it to llamacpp_models in Settings."
        )
        return RerankerRuntimeStatus("missing", reason)

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        """Re-score *results* with the router model.

        Args:
            query: The search query.
            results: Candidate rows, each with a ``text`` key.
            top_k: Number of rows to return.

        Returns:
            Rows sorted by the router score, truncated to ``top_k``, each with
            ``_reranked`` true; or, on any failure, the inputs in their order,
            truncated, with ``_reranked`` false.
        """
        self.last_failure_reason = None
        if not results:
            return results
        try:
            scores = self._scores(query, [row["text"] for row in results])
        except Exception as exc:  # noqa: BLE001 - the contract never raises
            self.last_failure_reason = f"llama.cpp rerank failed: {exc}"
            logger.warning("%s. Returning un-reranked results.", self.last_failure_reason)
            for row in results:
                row["_reranked"] = False
            return results[:top_k]
        for row, score in zip(results, scores, strict=True):
            row["score"] = score
            row["_reranked"] = True
        results.sort(key=lambda row: row["score"], reverse=True)
        return results[:top_k]

    def _scores(self, query: str, documents: list[str]) -> list[float]:
        """Return one score per document, in input order.

        Raises:
            httpx.HTTPError: On a refused connection or an HTTP error status.
            ValueError: When the reply does not score every document once
                with a probability.
        """
        url = f"{self.router_url.rstrip('/')}/rerank"
        body = {"model": self.model_id, "query": query, "documents": documents}
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=body, headers={"Authorization": "Bearer no-key"})
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # The status line alone hides the cause (for example a full KV cache).
                raise httpx.HTTPStatusError(
                    f"{exc}; server said: {response.text[:_ERROR_BODY_CHARS]}",
                    request=exc.request,
                    response=exc.response,
                ) from None
            reply = response.json()
        scores: dict[int, float] = {}
        for item in reply.get("results") or []:
            index, score = item.get("index"), item.get("relevance_score")
            if not isinstance(score, int | float) or not 0.0 <= score <= 1.0:
                raise ValueError(f"relevance_score {score!r} is not a probability in [0, 1]")
            scores[index] = max(float(score), math.ulp(0.0))
        if sorted(scores) != list(range(len(documents))):
            raise ValueError(
                f"the reply scored indexes {sorted(scores)} for {len(documents)} documents"
            )
        return [scores[i] for i in range(len(documents))]
