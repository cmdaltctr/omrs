"""Engine internals that live outside ``engine.py`` to keep it under the file-size ceiling.

* :func:`release_resources` is the body of ``Engine.close()``.
* :func:`graph_host` describes the Engine's resources to graph runs.
* :func:`install_as_process_default` is the legacy process-default installer.

Nothing here is public: the Engine is the only caller.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from .compose_pipelines import build_graph_host
from .engine_answer import judge_provider_of, recording_answer_llm, recording_judge
from .engine_embedders import embedding_for

if TYPE_CHECKING:
    from .engine import Engine

logger = logging.getLogger(__name__)


def release_resources(engine: Engine) -> None:
    """Drop caches, close the owned store and OCR client, release references.

    A store or OCR ``close()`` failure is logged, not raised, so the reference
    release always completes (ADR-061). Shared process-wide caches (the
    reranker model cache) are untouched.

    Args:
        engine: The Engine that is being closed. Its graph state is already
            released.
    """
    # Drop the engine-owned query embedding cache.
    engine._query_cache.clear()
    # Evict BM25 cache entries for this store's identity only.
    from .core.retrieval.sparse import evict_bm25_cache

    evict_bm25_cache(engine._store.cache_identity)
    try:
        engine._store.close()
    except Exception as exc:
        logger.warning(
            "store close() failed during engine close: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
    # Close the owned OCR worker client (task 2.6a): stop accepting
    # requests, close stdin, bounded graceful wait, then terminate.
    if engine._ocr_client is not None:
        try:
            engine._ocr_client.close()
        except Exception as exc:
            logger.warning(
                "OCR worker client close() failed during engine close: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
    # The embedder reference must go so a closed engine never pins model resources.
    engine._store = None  # type: ignore[assignment]
    engine._embed_model = None  # type: ignore[assignment]
    engine._embedders.release()
    engine._reranker = None
    engine._profile_resolver = None
    engine._profile_resolver_factory = None
    engine._answer_llm = None
    engine._answer_llm_factory = None
    engine._verify_llm_factory = None
    engine._ocr_client = None


def host_ocr(engine: Engine, settings: Any) -> Any:
    """Return the OCR routes of a standard ingest with *settings*.

    A composed client wins. Otherwise the routes come from the Engine's OCR
    client pool, so the host routes and a graph node with the same engine
    share one client (design D5 of integrations-show-runtime-components).
    """
    if engine._ocr_client is not None:
        return engine._ocr_client
    return engine._pipelines.ocr_pool().routes(settings)


def resolve_bound(engine: Engine, collection: str) -> tuple[Any, Any]:
    """Resolve the settings and the profile binding of a collection with one tag read.

    The binding is ``None`` when the Engine has no resolver or the resolver
    does not report bindings. A caller that finds a user binding runs the
    profile's pipelines; every other caller keeps the direct path.
    """
    from .core.profiles.resolver import ProfileResolver

    resolver = engine._resolver()
    if resolver is None:
        return engine._effective_settings, None
    if not isinstance(resolver, ProfileResolver):
        return resolver.resolve(collection), None
    return resolver.resolve_bound(collection)


def graph_host(engine: Engine, collection: str | None) -> Any:
    """Describe the Engine's resources to graph validation and runs.

    The embedder is the one the collection's profile names (ADR-081), so
    preflight and the steps use the model that made the collection's vectors.

    Args:
        engine: The Engine.
        collection: Default collection for nodes that name none.
    """
    # Bind to the generation current now, so a run that started keeps its model
    # when a provider update replaces the generation (design D3).
    generation = engine._gen
    answer_llm = generation.get_answer_llm if generation.answer_llm_factory is not None else None
    settings = engine._effective_settings
    embedder, choice = embedding_for(engine, collection)
    resources = {
        "store": engine._store,
        "embedder": embedder,
        "embedding_identity": choice or engine._embedders.host_identity,
        "reranker": engine._reranker,
        "ocr": engine._ocr_client
        if engine._ocr_client is not None
        else engine._pipelines.ocr_pool(),
        "answer_llm": recording_answer_llm(answer_llm, settings.answer.provider.strip()),
        "verify_llm": recording_judge(
            engine._pipelines.judge(generation.verify_llm_factory), judge_provider_of(settings)
        ),
    }
    from dataclasses import replace

    from .core.pipelines import HostOptionSet

    readers = HostOptionSet(
        inherited=engine._effective_settings.pdf_reader,
        unavailable={n: r for n, r in engine._pipelines.reader_options().items() if r},
    )
    graph = build_graph_host(
        engine._effective_settings,
        resources=resources,
        resolver=engine._resolver(),
        collection=collection,
    )
    options = {"pdf_reader": readers, **engine_option_sets(settings)}
    return replace(graph, host=replace(graph.host, options=options))


class EngineReasons(Mapping[str, str]):
    """Unprovisioned OCR engines and why, probed under the host workers folder.

    Iteration lists the engine folders and the host engine names that cannot
    run. A lookup also probes any other name, so admission refuses a node
    that names an engine with no folder at all.
    """

    def __init__(self, workers_dir: str, names: list[str]) -> None:
        """Probe the listed engines now.

        Args:
            workers_dir: The host ``ocr_workers_dir``.
            names: The host engine names, listed even without a folder.
        """
        from .capabilities import ocr_engine_options

        self._workers_dir = workers_dir
        self._listed = {
            o["name"]: o["reason"] for o in ocr_engine_options(workers_dir, names) if o["reason"]
        }

    def __getitem__(self, name: str) -> str:
        """Return why engine *name* cannot run; ``KeyError`` when it can."""
        from .capabilities import ocr_engine_options

        if name in self._listed:
            return self._listed[name]
        found = [o for o in ocr_engine_options(self._workers_dir, [name]) if o["name"] == name]
        if not found or found[0]["reason"] is None:
            raise KeyError(name)
        return found[0]["reason"]

    def __iter__(self) -> Iterator[str]:
        """Iterate over the listed engines that cannot run."""
        return iter(self._listed)

    def __len__(self) -> int:
        """Return the number of listed engines that cannot run."""
        return len(self._listed)


def engine_option_sets(settings: Any) -> dict[str, Any]:
    """Return the host option sets of the two OCR engine settings (design D4).

    The probe runs now, so an engine provisioned after start-up is usable
    without a restart.
    """
    from .core.pipelines import HostOptionSet

    primary, fallback = settings.ocr_engine_primary, settings.ocr_engine_fallback
    reasons = EngineReasons(settings.ocr_workers_dir, [primary, fallback])
    remedy = "Choose another engine or Inherit."
    return {
        "ocr_engine_primary": HostOptionSet(primary or None, reasons, remedy),
        "ocr_engine_fallback": HostOptionSet(fallback or None, reasons, remedy),
    }


def install_as_process_default(engine: Engine) -> None:
    """Install the Engine's components as process defaults (legacy transports)."""
    from llama_index.core import Settings as LlamaIndexSettings

    from .core.settings import set_default_effective_settings
    from .core.vectordb import set_default_store

    LlamaIndexSettings.embed_model = engine._embed_model
    set_default_store(engine._store)
    set_default_effective_settings(engine._effective_settings)
