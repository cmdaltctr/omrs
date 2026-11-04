"""Page-unit OCR routing for the pdf-inspector path (change page-level-ocr-routing).

The ``page`` unit routes a PDF page by page; it is the only unit (change
page-routing-default). This module holds that unit's logic beside the seam
in ``ocr_routing.py``: per-page evidence from a full scan, the local OCR
tier with its post-check escalation (tasks 4.2 and 4.2a; the backends and
their chain live in ``local_ocr/``, change local-ocr-backends), the counts and
backend of the merge, and one
document per page with text (change pdf-inspector-page-provenance, D5).

Page numbering is the trap here. pdf-inspector numbers
``extract_pages_markdown`` pages from **0** and ``process_pdf_with_ocr``
pages from **1**. Everything this module emits is 1-based, matching the OCR
API and the page labels readers already carry, so a page routed here is the
page that gets read.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_ocr import chain as local_ocr_chain
from .local_ocr import registry as local_ocr_registry
from .local_ocr.base import LocalOcrPage
from .script_routing import non_latin_output_reason, routing_mode

logger = logging.getLogger(__name__)

#: Page sources, in tier order. ``blank`` names a page the blank test
#: removed from the route before any OCR tier; ``unresolved`` means no
#: tier produced text.
PAGE_SOURCE_NATIVE = "native"
PAGE_SOURCE_LOCAL = "local"
PAGE_SOURCE_WORKER = "worker"
PAGE_SOURCE_BLANK = "blank"
PAGE_SOURCE_UNRESOLVED = "unresolved"

#: ``ocr_backend`` values. ``pdf_inspector_ocr`` names pdf-inspector's selective
#: OCR, which is not the worker. A worker page names the answering engine's
#: ``backend_id`` and a local page its backend's producer (change
#: local-ocr-backends). ``mixed`` is emitted when more than one backend produced
#: text: naming the highest tier instead would report the worker for a 200-page
#: document it read one page of.
OCR_BACKEND_FAST_PATH = "pdf_inspector"
OCR_BACKEND_LOCAL_OCR = "pdf_inspector_ocr"
OCR_BACKEND_MIXED = "mixed"

#: Page keys a page document carries. A document whose text spans the
#: whole PDF (the worker's response) must carry neither.
PAGE_KEYS = ("page", "page_label")

#: Page source -> the backend that produced it, when the page names no producer.
#: ``unresolved`` names none, and a worker page always names its engine.
_SOURCE_BACKENDS = {
    PAGE_SOURCE_NATIVE: OCR_BACKEND_FAST_PATH,
    PAGE_SOURCE_LOCAL: OCR_BACKEND_LOCAL_OCR,
}

#: Page source -> its metadata count key. The five sum to ``page_count``.
#: ``blank`` sits between the tiers and ``unresolved``: a blank page ran
#: no engine, and it is not a failure.
_COUNT_KEYS = {
    PAGE_SOURCE_NATIVE: "ocr_pages_native",
    PAGE_SOURCE_LOCAL: "ocr_pages_local",
    PAGE_SOURCE_WORKER: "ocr_pages_worker",
    PAGE_SOURCE_BLANK: "ocr_pages_blank",
    PAGE_SOURCE_UNRESOLVED: "ocr_pages_unresolved",
}


@dataclass(frozen=True)
class PageEvidence:
    """One page's OCR evidence from a full scan.

    Attributes:
        page: 1-based page number.
        markdown: The page's native pdf-inspector Markdown, possibly empty.
        needs_ocr: Whether the scan flagged this page as needing OCR.
        reason: The scan's stated reason, when it gave one.
    """

    page: int
    markdown: str
    needs_ocr: bool
    reason: str | None


def page_evidence(file: Path) -> list[PageEvidence]:
    """Return per-page OCR evidence from a scan of every page.

    The ``page`` unit takes no sampled evidence and applies no page-fraction
    threshold: every flagged page is handled, so every page is scanned.

    Args:
        file: Path to the PDF file.

    Returns:
        One :class:`PageEvidence` per page, in page order, numbered from 1.

    Raises:
        ImportError: If ``pdf_inspector`` is not installed.
        Exception: Whatever the scan raises. The page unit cannot fall back
            to sampled evidence, because the scan is the only evidence it
            has. Swallowing the failure would route nothing and call the
            file clean.
    """
    try:
        import pdf_inspector
    except ImportError as exc:  # pragma: no cover - mirrors the adapter's message
        raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

    scan = pdf_inspector.extract_pages_markdown(str(file))
    return [
        PageEvidence(
            # +1: the library numbers these pages from 0, the OCR API from 1.
            page=page.page + 1,
            markdown=page.markdown or "",
            needs_ocr=bool(page.needs_ocr),
            reason=getattr(page, "ocr_reason", None),
        )
        for page in scan.pages
    ]


def local_ocr(
    file: Path, pages: list[int], *, settings: Any, post_checks: Sequence | None = None
) -> list[LocalOcrPage]:
    """OCR each flagged page with the listed local OCR backends, in list order.

    Tier 1 of the ``page`` unit. The chain (``local_ocr/chain.py``, change
    local-ocr-backends, design D8) reads the pages with the backends of
    ``ocr_local_backends`` and runs the post-check escalation (design decision
    4) with each backend's effective cut. The default list is
    ``pp-ocrv6-small``: pdf-inspector's selective OCR in ``force`` mode on the
    1-based page list, exactly the call Experiment 33 task 6.7 measured.

    Args:
        file: Path to the PDF file.
        pages: 1-based page numbers to OCR. Uniqueness and order are the
            caller's guarantee; the evidence scan emits sorted uniques.
        settings: Injected settings carrying the backend list, the optional cut
            override and each backend's own fields.
        post_checks: The page rules' post-checks, each ``check(text, facts)``,
            or ``None``. ``None`` gives the non-Latin check under ``detect``.

    Returns:
        One :class:`LocalOcrPage` per page, in page order.

    Raises:
        ImportError: The only listed backend is not installed.
        Exception: No listed backend could read. Degradation for a missing
            runtime is the caller's (task 4.6); the tier only reports it.
    """
    if post_checks is None:
        post_checks = (non_latin_output_reason,) if routing_mode(settings) == "detect" else ()
    return local_ocr_chain.read_local_pages(file, pages, settings=settings, post_checks=post_checks)


# ── Switch-off and the local model resolution probe (task 4.2, identity) ──

#: The backend a one-argument call means (the head of the default list).
DEFAULT_BACKEND = local_ocr_registry.DEFAULT_BACKENDS[0]


def switch_local_tier_off(reason: str, backend: str = DEFAULT_BACKEND) -> None:
    """Switch *backend* off for the rest of this process.

    A runtime panic (``pyo3_runtime.PanicException``, a BaseException) poisons
    the engine's lock, so every later call panics again: after one, the backend
    and its identity probe stay off until the process restarts (change
    page-routing-default). The state lives in the local OCR registry, per backend.
    """
    local_ocr_registry.switch_off(backend, reason)


def local_tier_off_reason(settings: Any = None) -> str | None:
    """Return why the local tier is off for this process, or ``None``.

    The tier is off only when every listed backend is off; the reason is the
    first listed backend's. Without *settings*, the default list is read.
    """
    reasons = [local_ocr_registry.off_reason(name) for name in local_ocr_registry.listed(settings)]
    if not reasons or any(reason is None for reason in reasons):
        return None
    return reasons[0]


_RESOLUTION_LOCK = threading.Lock()
#: Process-wide cache of resolved local model identities, keyed by the backend
#: and the ``(model_directory, offline)`` pair the probe ran under. A different
#: backend or pair is a different model and must resolve afresh. Only successful
#: identities are cached: an unresolved runtime is re-probed, so the identity is
#: gained the moment the runtime appears and the index identity follows.
_local_model_resolution: dict[tuple[str, str, bool], str] = {}


def reset_local_model_resolution() -> None:
    """Clear the cached local model resolution.

    Test seam, matching the reranker's ``reset_model_cache`` contract: the
    cache is process state, and a test that stubs the engine needs to start
    from a blank slate and leave one behind.
    """
    with _RESOLUTION_LOCK:
        _local_model_resolution.clear()


def resolve_local_model_identity(settings: Any, backend: str = DEFAULT_BACKEND) -> str | None:
    """Resolve a local OCR backend's ``name@revision``, once per backend and settings pair.

    The backend's ``identity`` probe runs with the same model directory and
    offline mode the tier would use. A failed probe returns ``None`` and caches
    nothing, so the next call re-probes and the identity is gained the moment
    the runtime appears: reindexing exactly when the emitted text would change.
    Lock-guarded because ingest operations run on worker threads.

    Args:
        settings: Injected settings carrying ``ocr_local_model_directory``
            and ``ocr_local_offline``.
        backend: The backend name; the default backend when omitted.

    Returns:
        The resolved ``name@revision``, or ``None`` when unresolvable.
    """
    if local_ocr_registry.off_reason(backend) is not None:
        # The backend no longer reads pages, so its model may not vouch for text.
        return None
    key = (backend, settings.ocr_local_model_directory or "", bool(settings.ocr_local_offline))
    with _RESOLUTION_LOCK:
        cached = _local_model_resolution.get(key)
        if cached is not None:
            return cached
        # The default backend is probed with one argument, so a test stub of the
        # one-argument probe keeps working.
        extra = () if backend == DEFAULT_BACKEND else (backend,)
        identity = _probe_local_model_identity(settings, *extra)
        if identity is not None:
            _local_model_resolution[key] = identity
        return identity


def _probe_local_model_identity(settings: Any, backend: str = DEFAULT_BACKEND) -> str | None:
    """Run *backend*'s identity probe; a failure is ``None`` with a warning."""
    if local_ocr_registry.off_reason(backend) is not None:
        return None
    try:
        return local_ocr_registry.BACKENDS.get(backend).identity(settings)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - an unresolvable runtime is a None, not a failure
        if not isinstance(exc, Exception):
            switch_local_tier_off(f"{type(exc).__name__}: {exc}", backend)
        logger.warning(
            "Local OCR model identity unresolved (%s: %s); the index identity "
            "omits the model until the local OCR runtime is available",
            type(exc).__name__,
            exc,
        )
        return None


@dataclass(frozen=True)
class PageResult:
    """One page after routing, with the tier that produced its text.

    Attributes:
        page: 1-based page number.
        text: The page's text, possibly empty.
        source: One of the ``PAGE_SOURCE_*`` values.
        producer: The ``ocr_backend`` value of what produced ``text``: the
            worker's engine, the local backend that kept the page, or the local
            backend whose text an unresolved page kept.
    """

    page: int
    text: str
    source: str
    producer: str | None = None


@dataclass(frozen=True)
class MergedDocument:
    """One PDF's pages merged into the document the reader emits.

    Attributes:
        text: Page texts in page order, separated by a blank line.
        counts: The five page-source counts, summing to the page count.
        ocr_backend: The one backend that produced the text, or ``mixed``.
        ocr_used: Whether OCR produced the text of at least one page.
    """

    text: str
    counts: dict[str, int]
    ocr_backend: str
    ocr_used: bool


def merge_pages(pages: list[PageResult], *, page_count: int) -> MergedDocument:
    """Merge routed pages into one document.

    Pages join in the file's order, never the order the tiers finished in,
    separated by a blank line so a heading at the top of one page does not
    fuse into the previous page's last paragraph. A page with no text
    contributes nothing rather than an empty paragraph.

    Args:
        pages: One result per page, in any order.
        page_count: The PDF's page count, used to account for pages no tier
            reported.

    Returns:
        The merged text, the five page-source counts, and the diagnostics
        that describe them.
    """
    ordered = sorted(pages, key=lambda result: result.page)
    text = "\n\n".join(result.text for result in ordered if result.text)

    counts = dict.fromkeys(_COUNT_KEYS.values(), 0)
    for result in ordered:
        counts[_COUNT_KEYS[result.source]] += 1
    # A page no tier reported is a page nothing resolved, so the counts
    # always account for the whole document.
    reported = sum(counts.values())
    if reported < page_count:
        counts["ocr_pages_unresolved"] += page_count - reported

    # Only a page that produced text names a backend: a page nothing could
    # read is not evidence for any engine.
    backends = {
        result.producer or _SOURCE_BACKENDS[result.source]
        for result in ordered
        if result.text and (result.producer or result.source in _SOURCE_BACKENDS)
    }
    if len(backends) == 1:
        backend = next(iter(backends))
    elif backends:
        backend = OCR_BACKEND_MIXED
    else:
        # Nothing produced text. The fast path is what ran.
        backend = OCR_BACKEND_FAST_PATH
    ocr_used = bool(backends - {OCR_BACKEND_FAST_PATH})
    return MergedDocument(text=text, counts=counts, ocr_backend=backend, ocr_used=ocr_used)


def page_documents(pages: list[PageResult], metadata: dict[str, Any]) -> list:
    """Return one document per routed page with text, in page order.

    Change pdf-inspector-page-provenance, design D5: the page unit keeps
    each page's number, whichever tier read it, so search can name the
    page. A page with no text from any tier emits no document. Every
    document carries the same whole-PDF *metadata* (the counts and the
    diagnostics), plus its own ``page`` and ``page_label``.

    Args:
        pages: One result per page, in any order.
        metadata: The whole-PDF metadata every page document carries.

    Returns:
        The page documents, possibly empty.
    """
    from llama_index.core import Document

    base = {key: value for key, value in metadata.items() if key not in PAGE_KEYS}
    return [
        Document(
            text=result.text, metadata={**base, "page": result.page, "page_label": str(result.page)}
        )
        for result in sorted(pages, key=lambda result: result.page)
        if result.text.strip()
    ]
