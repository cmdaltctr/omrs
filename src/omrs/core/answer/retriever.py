"""Answer-side adapter over :func:`omrs.core.retrieval.search`.

Runs the existing ``search()`` path (profile-resolved levers, hybrid
fusion, reranking, context assembly) for the answer pipeline, so
answering has no retrieval code of its own (design D3, ADR-057).  The
raw rows carry lineage; the pipeline builds evidence and citations from
them (``evidence.py``, ``citations.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class SearchRetriever:
    """Adapter that runs ``search()`` with the answer's retrieval arguments.

    Constructed with the retrieval arguments ``answer()`` accepts and
    queried with ``retrieve(query)``.  The raw search rows are kept on
    :attr:`rows`; the pipeline builds its evidence list from them.
    """

    def __init__(
        self,
        *,
        search_fn: Callable[..., list[dict]] | None = None,
        collection_name: str = "documents",
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        rerank: bool | None = None,
        hybrid: bool | None = None,
        expand_window: int = 0,
        metadata_filter: dict | None = None,
        reranker: Any = None,
        store: Any = None,
        effective_settings: Any = None,
        embed_model: Any = None,
        query_cache: Any = None,
        embedding_identity: Any = None,
    ) -> None:
        """Store the retrieval arguments; nothing runs until ``retrieve``.

        Args:
            search_fn: Retrieval entry point (dependency injection for
                tests; defaults to ``core.retrieval.search``).
            collection_name: Collection to search.
            top_k: Maximum chunks to return (profile default when None).
            similarity_threshold: Minimum score to include.
            rerank: Tri-state rerank control.
            hybrid: Tri-state hybrid fusion control.
            expand_window: Neighbours merged into each chunk by context
                assembly.
            metadata_filter: Store ``where`` clause.
            reranker: Optional pre-constructed reranker.
            store: Optional injected vector store.
            effective_settings: Optional resolved profile settings.
            embed_model: Optional injected embedding model (the engine's
                embedder); ``None`` selects the legacy global path.
            query_cache: Optional engine-owned query embedding cache.
            embedding_identity: Provider and model that embed the query
                (ADR-081); sent to ``search`` only when set.
        """
        self._search_fn = search_fn
        self._collection_name = collection_name
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold
        self._rerank = rerank
        self._hybrid = hybrid
        self._expand_window = expand_window
        self._metadata_filter = metadata_filter
        self._reranker = reranker
        self._store = store
        self._effective_settings = effective_settings
        self._embed_model = embed_model
        self._query_cache = query_cache
        self._embedding_identity = embedding_identity
        # Raw search rows from the last retrieve() call.
        self.rows: list[dict] = []

    def retrieve(self, query: str) -> list[dict]:
        """Run ``search()``, keep the rows on :attr:`rows` and return them."""
        if self._search_fn is None:
            from ..retrieval.pipeline import search as _search
        else:
            _search = self._search_fn

        identity = self._embedding_identity
        identity_kwargs = {"embedding_identity": identity} if identity else {}
        self.rows = _search(
            query,
            top_k=self._top_k,
            similarity_threshold=self._similarity_threshold,
            rerank=self._rerank,
            hybrid=self._hybrid,
            expand_window=self._expand_window,
            collection_name=self._collection_name,
            metadata_filter=self._metadata_filter,
            reranker=self._reranker,
            store=self._store,
            effective_settings=self._effective_settings,
            embed_model=self._embed_model,
            query_cache=self._query_cache,
            **identity_kwargs,
        )
        return self.rows
