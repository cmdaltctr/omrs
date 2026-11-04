"""Per-source port value and shared helpers of the ingestion graph adapters.

One :class:`SourceWork` value travels from ``source.identify`` to
``commit.source`` for exactly one source unit. Each adapter returns a new
value with ``dataclasses.replace``. A value whose ``status`` is not
``pending`` (an unchanged or binary source) passes through every node
without work, so the commit can report the same per-source outcome as
``ingest_path_async``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from ..pipelines import NodeContext, PipelineCancelledError
from ..reading_lists import engine_list, expand_ocr_engines, expand_pdf_reader
from ..settings import EffectiveSettings
from .backends.orchestrator import BackendRead
from .commit import PreparedSource
from .graph_adapters_catalogue import READ_OPTION_KEYS
from .sources import SourceIdentity, SourceUnit

#: Engine resource names used by the ingestion adapters.
STORE_RESOURCE = "store"
EMBEDDER_RESOURCE = "embedder"
EMBEDDING_IDENTITY_RESOURCE = "embedding_identity"
OCR_RESOURCE = "ocr"

PENDING = "pending"
UNCHANGED = "unchanged"
BINARY = "binary"

_T = TypeVar("_T")


@dataclass(frozen=True)
class SourceWork:
    """The state of one source unit between identify and commit.

    Attributes:
        unit: The discovered source unit.
        collection: Collection the reuse check ran against.
        status: ``pending``, ``unchanged`` (complete current version) or
            ``binary`` (detected binary; the commit removes its rows).
        identity: Canonical source and index identity (``None`` for binary).
        existing_chunks: Stored chunk count of an unchanged source.
        backend_read: Reader output with its declarations.
        nodes: Chunked nodes (specialised strategy or splitter).
        specialised: Whether a code/config strategy produced ``nodes``.
        effective_strategy: Strategy a code chunk result reports, if any.
        doc_metadata: File-level metadata from ``prepare.enrich``.
        metadata_degraded: Whether metadata came from a fallback tier.
        prepared: The prepared attempt record from ``embed.chunks``.
    """

    unit: SourceUnit
    collection: str
    status: str = PENDING
    identity: SourceIdentity | None = None
    existing_chunks: int = 0
    backend_read: BackendRead | None = None
    nodes: list | None = None
    specialised: bool = False
    effective_strategy: str | None = None
    doc_metadata: dict | None = None
    metadata_degraded: bool = False
    prepared: PreparedSource | None = None

    @property
    def pending(self) -> bool:
        """Return whether this source still needs work."""
        return self.status == PENDING

    def require_identity(self) -> SourceIdentity:
        """Return the identity of a pending source.

        Raises:
            ValueError: If ``source.identify`` did not run for this value.
        """
        if self.identity is None:
            raise ValueError(
                f"Source {self.unit.rel_path!r} has no identity. Connect source.identify "
                "before this node."
            )
        return self.identity


def single_unit(value: Any) -> SourceUnit:
    """Return the one source unit of a per-unit pass.

    The runner delivers one unit as a one-item tuple under a ``UnitSplit``.

    Raises:
        ValueError: If the value holds more or less than one source unit.
        TypeError: If the value is not a source unit.
    """
    if isinstance(value, SourceUnit):
        return value
    items = list(value) if isinstance(value, Sequence) and not isinstance(value, str) else None
    if items is None or len(items) != 1:
        count = "an unknown number of" if items is None else str(len(items))
        raise ValueError(
            f"source.identify takes one source unit per pass; it received {count}. Run the "
            "graph with a unit split on discover.sources so each source is processed alone."
        )
    if not isinstance(items[0], SourceUnit):
        raise TypeError(f"Expected a SourceUnit, not {type(items[0]).__name__}.")
    return items[0]


def work_value(value: Any) -> SourceWork:
    """Return *value* as :class:`SourceWork`.

    Raises:
        TypeError: If an upstream node produced another value type.
    """
    if not isinstance(value, SourceWork):
        raise TypeError(
            f"Expected the per-source value from source.identify, not {type(value).__name__}."
        )
    return value


def required(context: NodeContext, name: str) -> Any:
    """Return a host resource and refuse a ``None`` placeholder.

    Raises:
        LookupError: If the host did not supply the resource.
    """
    value = context.resource(name)
    if value is None:
        raise LookupError(f"Node {context.node_id!r} needs resource {name!r}, but it is None.")
    return value


def optional(context: NodeContext, name: str) -> Any:
    """Return a host resource, or ``None`` when the host did not supply it."""
    return context.resources.get(name)


def _step_lists(settings: EffectiveSettings, update: Mapping[str, Any]) -> dict[str, Any]:
    """Return the list and single-value fields that the step options in *update* set.

    ``EffectiveSettings`` has no auto-fill, so compose fills ``pdf_readers`` and
    ``ocr_engines`` from the host. A copy that only changed ``pdf_reader`` would
    keep the stale host list, and readers of the list would ignore the step. This
    sets both forms together: the list from the step, and the single-value keys
    from the list, as ``Settings`` does for a list it receives.

    A single-value engine option replaces its entry in the host list. The
    other entry stays the host's, and later host entries drop out, because the
    single-value form means at most two engines.
    """
    fields: dict[str, Any] = {}
    readers = update.get("pdf_readers") or (
        expand_pdf_reader(update["pdf_reader"]) if "pdf_reader" in update else ()
    )
    if readers:
        fields.update(pdf_readers=tuple(readers), pdf_reader=readers[0])
    engines = update.get("ocr_engines")
    if not engines and ("ocr_engine_primary" in update or "ocr_engine_fallback" in update):
        host = engine_list(settings)
        engines = expand_ocr_engines(
            update.get("ocr_engine_primary", host[0] if host else ""),
            update.get("ocr_engine_fallback", host[1] if len(host) > 1 else ""),
        )
    if engines:
        fields.update(
            ocr_engines=tuple(engines),
            ocr_engine_primary=engines[0],
            ocr_engine_fallback=engines[1] if len(engines) > 1 else "",
        )
    return fields


def with_read_options(settings: EffectiveSettings, params: Any) -> EffectiveSettings:
    """Return *settings* with every set read option of a Read document node.

    The read options are the reader keys and the OCR keys (``READ_OPTION_KEYS``).
    ``None`` inherits the host value. Without a set option, *settings* is
    returned unchanged. The copy leaves the frozen host settings alone. The
    read and identify adapters both use this helper, so the read and the
    stored identity use the same options.

    Args:
        settings: The node settings.
        params: The node's ``ReadParams``, or a mapping of option to value
            (the ``IngestionShape`` options of the identify step).
    """
    values = params if isinstance(params, Mapping) else dict(params)
    update = {k: v for k, v in values.items() if k in READ_OPTION_KEYS and v is not None}
    if not update:
        return settings
    return settings.model_copy(update={**update, **_step_lists(settings, update)})


def node_ocr(context: NodeContext, settings: EffectiveSettings) -> Any:
    """Return the OCR routes of a node with *settings*, or ``None``.

    The ``ocr`` resource is the Engine's OCR client pool: it gives the routes
    of the node's effective engines (design D5). A resource without
    ``routes`` (an injected client or route pair) is used as it is.
    """
    ocr = optional(context, OCR_RESOURCE)
    routes = getattr(ocr, "routes", None)
    return routes(settings) if callable(routes) else ocr


def target_collection(context: NodeContext, params: Any) -> str:
    """Return the admitted collection of a collection-bound node.

    Raises:
        LookupError: If neither admission nor the parameters name one.
    """
    collection = context.collection or getattr(params, "collection", None)
    if not collection:
        raise LookupError(f"Node {context.node_id!r} has no target collection.")
    return collection


def stop_if_cancelled(context: NodeContext) -> None:
    """Stop at a safe boundary before a protected commit starts.

    Raises:
        PipelineCancelledError: If the run requested cancellation.
    """
    if context.cancellation.cancelled:
        raise PipelineCancelledError(
            f"The run was cancelled before node {context.node_id!r} started its commit."
        )


async def run_protected(call: Callable[[], _T]) -> _T:
    """Run a blocking protected operation to completion in a worker thread.

    The operation cannot stop part-way. If the awaiting task is cancelled,
    this function waits until the operation has finished its write,
    verification and cleanup, then re-raises the cancellation.
    """
    task = asyncio.ensure_future(asyncio.to_thread(call))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()  # retrieved: the cancellation below is what we report
        raise
