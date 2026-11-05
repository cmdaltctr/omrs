"""OCR routing: the seam around pdf-inspector, page by page.

:class:`OcrRoutedPdfInspector` reads every PDF under the ``page`` routing
unit, the only unit (change page-routing-default): a full scan flags the
pages that need OCR, the blank test removes blank sheets, the local OCR
tier reads each remaining flagged page, and the pages it cannot read go to
the OCR routes in one page-listed request. Clean text-based PDFs, including
multi-column and table-heavy layouts, never dispatch: layout complexity is
not a routing input.

Every emitted document carries the OCR diagnostics ``ocr_required``,
``ocr_used``, ``ocr_backend`` and the scalar ``pages_needing_ocr``, plus the
five page-source counts.

Failure behaviour:

- a missing local OCR runtime sends the flagged pages to the OCR routes,
  never back to native text (issue #161);
- no OCR route before dispatch → the pages keep the best available text
  and count unresolved, with an actionable warning;
- worker failure AFTER dispatch → raise :class:`OcrPostDispatchError` so the
  existing per-file reader error boundary reports the file failed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..ocr_worker.client import OcrWorkerError
from ..ocr_worker.managed import UNAVAILABLE_CODE
from ..ocr_worker.protocol import PAGES_PROTOCOL_VERSION
from ..ocr_worker.routes import OcrRoutes, backend_id_of, request_timeout, route_role
from .page_routing import (
    PAGE_KEYS,
    PAGE_SOURCE_BLANK,
    PAGE_SOURCE_LOCAL,
    PAGE_SOURCE_NATIVE,
    PAGE_SOURCE_UNRESOLVED,
    PAGE_SOURCE_WORKER,
    LocalOcrPage,
    PageResult,
    local_ocr,
    local_tier_off_reason,
    merge_pages,
    page_documents,
    page_evidence,
)
from .page_rules.pipeline import run_rules

logger = logging.getLogger(__name__)

#: A rescued document was read by pdf-inspector alone. A worker result
#: names the answering engine's ``backend_id`` (design D6).
OCR_BACKEND_FAST_PATH = "pdf_inspector"


class OcrPostDispatchError(RuntimeError):
    """A worker failure after a complete request was written and flushed.

    Attributes:
        code: The structured worker failure code (``timeout``,
            ``worker_crashed``, ``worker_closed_output``,
            ``protocol_violation``, or a worker-reported code).
        message: Human-readable description for the per-file error.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"ocr_worker.{code}: {message}")
        self.code = code
        self.message = message


def _stamp_ocr_diagnostics(
    metadata: dict[str, Any],
    *,
    ocr_required: bool,
    ocr_used: bool,
    ocr_backend: str,
) -> None:
    """Stamp the four additive OCR diagnostic keys (task 2.10).

    ``pages_needing_ocr`` is already present as a scalar count from the
    pdf-inspector adapter; the other three are additive and never
    overwrite more authoritative existing values.
    """
    metadata["ocr_required"] = ocr_required
    metadata["ocr_used"] = ocr_used
    metadata["ocr_backend"] = ocr_backend


class OcrRoutedPdfInspector:
    """Routing seam around one pdf-inspector reader instance.

    Transparent to the reader registry: constructed by
    :func:`integrations.pdf.factory.build_pdf_reader` only when the
    resolved reader is ``pdf_inspector`` AND the operator enabled the
    OCR fallback. Everything else — the declared ``text_format``, the
    ``load_data`` contract — is the wrapped reader's.
    """

    def __init__(self, inner: Any, *, settings: Any, ocr_client: Any = None) -> None:
        """Wrap *inner* with the routing decision from injected settings.

        Args:
            inner: The concrete pdf-inspector reader instance.
            settings: Injected settings carrying the routing settings and
                the worker request timeout.
            ocr_client: Injected :class:`OcrRoutes` (engine- or
                operation-owned), or one managed client, which becomes a
                primary-only route pair. ``None`` means no worker is
                wired: OCR-required files degrade deterministically.
        """
        self._inner = inner
        self._settings = settings
        self._routes = OcrRoutes.of(ocr_client)

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Read one PDF page by page through the OCR tiers.

        Args:
            file: Path to the PDF file.
            *args: Forwarded to the wrapped reader.
            **kwargs: Forwarded to the wrapped reader.

        Returns:
            One document per page with text, each read by the highest tier
            that produced text for it and carrying the page-source counts
            and the four OCR diagnostics.

        Raises:
            OcrPostDispatchError: On any worker failure after the
                complete parse request was written and flushed.
            Exception: Whatever the wrapped reader raises (the existing
                reader error boundary applies unchanged).
        """
        documents = self._inner.load_data(file, *args, **kwargs)
        if not documents:
            return documents
        return self._page_unit_documents(file, documents)

    # ── The page routing unit (tasks 4.4, 4.5c, 4.6) ──────────────────

    def _page_unit_documents(self, file: Path, inner_documents: list) -> list:
        """Read one PDF page by page and emit one document per page.

        The full scan is the only evidence (task 4.1): every flagged page is OCRed locally
        (task 4.2), the pages the post-check rejects go to the worker in ONE request (task
        4.4), and the merge computes the counts and the backend (task 4.5c). Each page with
        text becomes its own document with its ``page`` (change
        pdf-inspector-page-provenance). A missing local runtime sends the flagged pages
        to the worker (page-routing-default, issue #161). Degradation never fails the file
        (task 4.6): a missing or unattributable worker keeps the best available text and
        counts the affected pages unresolved. Only a worker failure AFTER a complete request
        was flushed raises.

        Args:
            file: Path to the PDF file.
            inner_documents: The wrapped reader's documents; the first
                one's metadata is the base the counts and diagnostics join.

        Returns:
            One document per page with text, in page order, each carrying
            the five page-source counts and the OCR diagnostics. When no
            page has text, the wrapped reader's rescued documents, or one
            empty document.

        Raises:
            OcrPostDispatchError: On a worker failure after dispatch.
            Exception: Whatever the full scan raises — the page unit has
                no sampled evidence to fall back to.
        """
        from llama_index.core import Document

        inner_document = inner_documents[0]
        evidence = page_evidence(file)
        page_count = len(evidence)
        flagged = {entry.page for entry in evidence if entry.needs_ocr}
        # The page rules (blank, maths, non-Latin; design D5) run in order. A
        # dropped page keeps its native text and counts blank; a direct page
        # skips the local tier and joins the one worker request.
        plan = run_rules(
            file,
            evidence,
            flagged,
            self._settings,
            self._routes,
            judge=getattr(self._routes, "judge", None),
        )
        blank, direct, local_pages_wanted = plan.dropped, plan.direct, list(plan.local)

        results: list[PageResult] = []
        placed: set[int] = set()
        escalated: dict[int, LocalOcrPage | None] = dict.fromkeys(direct)
        no_tier = False  # neither tier can read the flagged pages; one warning said so
        local_error = local_tier_off_reason(self._settings) if local_pages_wanted else None
        if local_pages_wanted and local_error is None:
            local_pages, local_error = self._read_local(
                file, local_pages_wanted, plan.post_checks()
            )
            if local_error is None:
                for page in local_pages:
                    if page.escalates:
                        escalated[page.page] = page
                    else:
                        results.append(
                            PageResult(
                                page=page.page,
                                text=page.text,
                                source=PAGE_SOURCE_LOCAL,
                                producer=page.producer,
                            )
                        )
                        placed.add(page.page)
        if local_error is not None:
            # Native text on a flagged page may be a junk hidden layer, so a
            # missing local tier escalates every page it should have read.
            escalated.update(dict.fromkeys(local_pages_wanted))
            no_tier = self._routes.select(protocol=PAGES_PROTOCOL_VERSION) is None
            if no_tier:
                logger.warning(
                    "Local OCR tier unavailable for %s (%s) and no OCR route that speaks "
                    "protocol 1.1; %d flagged page(s) keep native text and count "
                    "unresolved. Install the local runtime, or provision an engine and "
                    "set OCR_WORKERS_DIR.",
                    getattr(file, "name", file),
                    local_error,
                    len(escalated),
                )
            else:
                logger.warning(
                    "Local OCR tier unavailable for %s (%s); %d flagged page(s) go to the OCR "
                    "routes",
                    getattr(file, "name", file),
                    local_error,
                    len(local_pages_wanted),
                )

        worker_text, backend = (
            self._escalated_worker_text(file, sorted(escalated))
            if escalated and not no_tier
            else ({}, None)
        )

        # Direct pages no engine read go to the degrade hook of the rule that
        # sent them first; the local tier reads what the hooks return, with no
        # post-check, because no engine can take an escalation now.
        unread = [page for page in sorted(direct) if not worker_text.get(page)]
        if unread and local_error is None and local_tier_off_reason(self._settings) is None:
            degraded = plan.degrade(unread)
            found = self._read_local(file, degraded, ())[0] if degraded else []
            for page in (page for page in found if page.text.strip()):
                results.append(
                    PageResult(
                        page=page.page,
                        text=page.text,
                        source=PAGE_SOURCE_LOCAL,
                        producer=page.producer,
                    )
                )
                placed.add(page.page)
                escalated.pop(page.page, None)

        for entry in evidence:
            if entry.page in placed:
                continue
            if entry.page in escalated:
                text = worker_text.get(entry.page, "")
                if text:
                    results.append(
                        PageResult(
                            page=entry.page, text=text, source=PAGE_SOURCE_WORKER, producer=backend
                        )
                    )
                else:
                    # The escalation did not resolve this page: the worker
                    # was missing, unattributable, or returned nothing. The
                    # best available text is kept; no marker is inserted.
                    # Kept local OCR text still names its producer.
                    local_page = escalated[entry.page]
                    local_text = local_page.text if local_page is not None else ""
                    results.append(
                        PageResult(
                            page=entry.page,
                            text=local_text if local_text.strip() else entry.markdown,
                            source=PAGE_SOURCE_UNRESOLVED,
                            producer=local_page.producer if local_text.strip() else None,
                        )
                    )
            elif entry.page in blank and entry.page in flagged:
                # The blank test removed this flagged page from the route.
                # It ran no OCR tier; its native text was empty on every
                # page the calibration measured, so it emits no document.
                # A page a later rule dropped after an earlier rule added it
                # was never flagged: it keeps its native text below.
                results.append(
                    PageResult(page=entry.page, text=entry.markdown, source=PAGE_SOURCE_BLANK)
                )
            elif entry.page in flagged:
                # The local tier returned no entry for this page; native text
                # is all there is.
                results.append(
                    PageResult(page=entry.page, text=entry.markdown, source=PAGE_SOURCE_UNRESOLVED)
                )
            else:
                results.append(
                    PageResult(page=entry.page, text=entry.markdown, source=PAGE_SOURCE_NATIVE)
                )

        merged = merge_pages(results, page_count=page_count)
        metadata = {k: v for k, v in inner_document.metadata.items() if k not in PAGE_KEYS}
        metadata["page_count"] = page_count
        # The complete scan is the page unit's authority on the count.
        metadata["pages_needing_ocr"] = len(flagged)
        _stamp_ocr_diagnostics(
            metadata,
            ocr_required=bool(flagged or direct),
            ocr_used=merged.ocr_used,
            ocr_backend=merged.ocr_backend,
        )
        metadata.update(merged.counts)
        plan.stamp(metadata, escalated.values())

        rescued = [doc for doc in inner_documents if doc.text]
        if not merged.text and rescued:
            # ADR-066 rescue of last resort: the scan produced no text on
            # any page, yet the wrapped reader recovered the document
            # through the fallback chain. That rescued text is the record;
            # the counts report every page native, a whole-document claim,
            # with ``extraction_fallback_backend`` naming the true origin.
            metadata.update(
                {
                    "ocr_pages_native": page_count,
                    "ocr_pages_local": 0,
                    "ocr_pages_worker": 0,
                    "ocr_pages_blank": 0,
                    "ocr_pages_unresolved": 0,
                }
            )
            _stamp_ocr_diagnostics(
                metadata,
                ocr_required=bool(flagged or direct),
                ocr_used=False,
                ocr_backend=OCR_BACKEND_FAST_PATH,
            )
            # Each rescued page keeps its own page keys.
            pages = [
                {k: doc.metadata[k] for k in PAGE_KEYS if k in doc.metadata} for doc in rescued
            ]
            return [
                Document(text=doc.text, metadata={**metadata, **page})
                for doc, page in zip(rescued, pages, strict=True)
            ]
        return page_documents(results, metadata) or [Document(text="", metadata=metadata)]

    def _read_local(
        self, file: Path, pages: list[int], post_checks: tuple
    ) -> tuple[list[LocalOcrPage], str | None]:
        """Run the local tier on *pages*; return its results and the error, if any.

        A missing runtime never fails the file: the error comes back as text. The
        chain has already switched a panicking backend off for the process.
        """
        try:
            return local_ocr(file, pages, settings=self._settings, post_checks=post_checks), None
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - a missing runtime never fails the file
            return [], f"{type(exc).__name__}: {exc}"

    def _escalated_worker_text(
        self, file: Path, pages: list[int]
    ) -> tuple[dict[int, str], str | None]:
        """Dispatch the escalated and maths pages in one request, per page.

        Args:
            file: Path to the PDF file.
            pages: 1-based page numbers, sorted.

        Returns:
            Page number to worker Markdown, and the answering engine's
            ``backend_id``. An empty dict means the
            escalation degraded: no route is available, the route cannot serve
            page-listed requests (it speaks a protocol older than
            ``PAGES_PROTOCOL_VERSION``), or its response cannot be
            attributed per page. All three keep the best available text
            and count the pages unresolved.

        Raises:
            OcrPostDispatchError: On a worker failure after the complete
                request was written and flushed.
        """
        name = getattr(file, "name", file)
        # Only a 1.1 route may receive a page-listed request: a 1.0 worker would
        # reject the envelope after dispatch and fail the file. A 1.0 primary
        # therefore passes the request to a 1.1 fallback.
        client = self._routes.select(protocol=PAGES_PROTOCOL_VERSION)
        if client is None:
            spoken = [
                f"{route_role(index)} speaks {fp.protocol_version}"
                for index, fp in enumerate(self._routes.fingerprints)
                if fp.available
            ]
            if spoken:
                logger.warning(
                    "%d escalated page(s) in %s need a worker that speaks protocol "
                    "%s, but no OCR route does (%s); page routing degrades and the "
                    "pages keep their best available text, counting unresolved. "
                    "Upgrade the worker to enable page-listed parsing.",
                    len(pages),
                    name,
                    PAGES_PROTOCOL_VERSION,
                    ", ".join(spoken),
                )
            else:
                logger.warning(
                    "%d escalated page(s) in %s have no OCR route; keeping the "
                    "best available text and counting them unresolved. Provision an "
                    "engine and set OCR_WORKERS_DIR to enable it.",
                    len(pages),
                    name,
                )
            return {}, None
        try:
            result = client.parse(
                str(file), pages=pages, timeout=request_timeout(self._settings, len(pages))
            )
        except OcrWorkerError as exc:
            if exc.code == UNAVAILABLE_CODE:  # refused before dispatch: no route (design D10)
                logger.warning("%d escalated page(s) in %s: %s", len(pages), name, exc.message)
                return {}, None
            raise OcrPostDispatchError(exc.code, exc.message) from exc
        pages_markdown = result.pages_markdown
        if pages_markdown is None or len(pages_markdown) != len(pages):
            logger.warning(
                "Worker response for %s cannot be attributed per page (pages_markdown "
                "absent or not parallel to the request); escalated pages keep their "
                "best available text and count unresolved",
                name,
            )
            return {}, None
        return dict(zip(pages, pages_markdown, strict=True)), backend_id_of(client)
