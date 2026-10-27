"""pdf-inspector adapter — Rust PDF classification and per-page markdown extraction.

pdf-inspector (Firecrawl, MIT) classifies a PDF as text-based, scanned,
image-based, or mixed in milliseconds, then extracts position-aware text
and converts it to structured markdown — multi-column reading order,
headings, lists, and tables — without OCR or ML models. Strong on the
two-column academic layouts the Qasper corpus (Experiment 14) is built
from.

The adapter makes two library calls per PDF (change
pdf-inspector-page-provenance, design D1): ``process_pdf`` supplies the
classification, the sampled OCR evidence and the silent-empty test;
``extract_pages_markdown`` supplies the page texts and, for long
``text_based`` PDFs, the full-scan OCR count. It emits one document per
page with text, carrying ``page`` (1-based int) and ``page_label`` (the
same number as a string), the format ``liteparse`` and ``pypdfium2`` use.

Base dependency and the configured default reader (ADR-050); the
import stays lazy inside ``load_data`` per the ADR-024 pattern shared
by the integrations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: pdf-inspector's default detection samples at most this many evenly
#: spread pages (``ScanStrategy::Sample(8)``); the Python binding exposes
#: no scan-strategy option. A ``text_based`` result on a longer PDF can
#: therefore miss image-only pages outside the sample (TDR-026).
PDF_INSPECTOR_SAMPLED_PAGES = 8


class PdfInspectorReader:
    """Adapter wrapping pdf-inspector for per-page markdown extraction.

    Produces one ``Document`` per page that has text, in page order. Each
    carries the page's markdown, ``page`` and ``page_label``, plus the
    whole-PDF classification diagnostics (``pdf_type``, ``pdf_confidence``,
    ``page_count``, ``pages_needing_ocr``) so downstream consumers can
    route on them (e.g. scanned PDFs to an OCR path). When the per-page
    result is unusable, the whole-document markdown is emitted as one
    document without page keys.
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF into page documents via pdf-inspector.

        Args:
            file: Path to the PDF file.

        Returns:
            One LlamaIndex ``Document`` per page with non-whitespace text,
            in page order, each carrying ``page`` and ``page_label``. When
            the per-page call raises or gives no text while the
            whole-document markdown has text, one document with that
            markdown and no page keys. When pdf-inspector classifies the
            file ``text_based`` yet extracts nothing from a non-empty page
            count, the documents are the fallback chain's recovered pages
            instead — liteparse first, pypdf last (ADR-066). When nothing
            has text, one document with empty text and no page keys, so
            callers observe the classification.

        Raises:
            ImportError: If ``pdf_inspector`` is not installed.
            Exception: Whatever the final pypdf tier raises — a file that
                opens in pdf-inspector but crashes pypdf is genuinely
                broken input for the per-file error boundary.
        """
        try:
            import pdf_inspector
        except ImportError as exc:
            raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

        from llama_index.core import Document

        result = pdf_inspector.process_pdf(str(file))
        markdown = result.markdown or ""
        scan = _extract_pages(pdf_inspector, file)
        # Store-compatible scalar count (task 2.10): vector-store
        # metadata values are scalars in both backends and nothing
        # sanitises them on the way in, so the classifier's page LIST
        # is reduced here to the count the routing gate consumes.
        pages_needing_ocr_count = len(_complete_ocr_pages(file, result, scan))

        metadata: dict[str, Any] = {
            "pdf_reader": "pdf_inspector",
            "pdf_type": result.pdf_type,
            "pdf_confidence": result.confidence,
            "page_count": result.page_count,
            "pages_needing_ocr": pages_needing_ocr_count,
            "file_path": str(file),
            "file_name": file.name,
        }

        if result.pdf_type != "text_based":
            logger.info(
                "pdf-inspector classified %s as %s (confidence %.2f, "
                "%d page(s) may need OCR); markdown may be partial",
                file.name,
                result.pdf_type,
                result.confidence,
                pages_needing_ocr_count,
            )

        # Sloman guard (design D6, change pdf-reader-extraction-fallback):
        # a ``text_based`` classification with an empty extraction on a
        # non-empty document is a contradiction — the classifier saw a
        # text layer the extractor failed to read (WinAnsi TrueType
        # without /ToUnicode; IA GlyphLessFont; TDR-024). Retry through
        # the tiered fallback chain — liteparse first (extraction-only,
        # fastest rescue), pypdf last (always available) — before
        # emitting zero characters (ADR-066; unqualified design numbers
        # below are D1–D5 of change tiered-reader-fallback-chain).
        if result.pdf_type == "text_based" and markdown == "" and result.page_count > 0:
            recovered, fallback_backend = _rescue_pages(file)
            if not recovered:
                logger.warning(
                    "pdf-inspector extracted no text from %s despite a "
                    "text_based classification, and both fallback tiers "
                    "recovered nothing — emitting the flagged "
                    "evidence unchanged for OCR routing",
                    file.name,
                )
                return [Document(text=markdown, metadata=metadata)]
            logger.warning(
                "pdf-inspector extracted no text from %s despite a "
                "text_based classification (%d page(s) flagged); "
                "recovered %d characters from %d page(s) via %s",
                file.name,
                pages_needing_ocr_count,
                sum(len(text) for _, _, text in recovered),
                len(recovered),
                fallback_backend,
            )
            # Evidence correction, not replacement (D4, change
            # pdf-reader-extraction-fallback): the pages were flagged only
            # by the failed extraction, so the scalar the OCR gate reads
            # drops to zero while the original count survives under a
            # diagnostic key.
            metadata["pages_needing_ocr"] = 0
            metadata["pages_needing_ocr_before_fallback"] = pages_needing_ocr_count
            metadata["extraction_fallback_backend"] = fallback_backend
            return [
                Document(text=text, metadata={**metadata, "page": page, "page_label": label})
                for page, label, text in recovered
            ]

        if scan is not None:
            if len(scan.pages) != result.page_count:
                logger.warning(
                    "pdf-inspector per-page result for %s has %d page(s) but the "
                    "document reports %d; numbering pages from the per-page result",
                    file.name,
                    len(scan.pages),
                    result.page_count,
                )
            page_documents = [
                Document(text=text, metadata={**metadata, "page": page, "page_label": str(page)})
                for page, text in _page_texts(scan)
            ]
            if page_documents:
                return page_documents

        # Safe floor (design D3): the per-page result is unusable, so emit
        # today's whole-document Markdown without page keys.
        if markdown.strip():
            logger.warning(
                "pdf-inspector per-page extraction gave no usable text for %s; "
                "emitting the whole-document markdown without page numbers",
                file.name,
            )
        return [Document(text=markdown, metadata=metadata)]


def _page_number(page: Any) -> int:
    """Return the 1-based page number of a ``PageMarkdown`` result.

    pdf-inspector numbers ``extract_pages_markdown`` pages from 0
    (``PageMarkdown.page``; checked on 1.17.0 in the change's
    ``evidence/library-check.txt``). OMRS pages count from 1, like
    ``liteparse`` and ``pypdfium2``.
    """
    return int(page.page) + 1


def _page_texts(scan: Any) -> list[tuple[int, str]]:
    """Return ``(page, markdown)`` for each page with non-whitespace text, in order."""
    pages = [(_page_number(page), page.markdown or "") for page in scan.pages]
    return [(page, text) for page, text in sorted(pages) if text.strip()]


def _extract_pages(pdf_inspector: Any, file: Path) -> Any | None:
    """Return the per-page extraction result, or ``None`` when the call fails.

    A failure here never fails the read: the caller falls back to the
    whole-document markdown and the sampled OCR evidence.
    """
    try:
        return pdf_inspector.extract_pages_markdown(str(file))
    except Exception as exc:  # noqa: BLE001 - per-page extraction must never fail the read
        logger.warning(
            "pdf-inspector per-page extraction failed for %s (%s); falling back "
            "to the whole-document markdown without page numbers",
            file.name,
            type(exc).__name__,
        )
        return None


def _rescue_pages(file: Path) -> tuple[list[tuple[int, str, str]], str | None]:
    """Run the silent-empty fallback chain and keep one entry per recovered page.

    Change pdf-inspector-page-provenance, design D4: each recovered page
    stays its own document. liteparse pages keep their own ``page`` and
    ``page_label`` (already physical and 1-based). pypdf pages are numbered
    by their position in the file, counted before empty pages are dropped,
    because its own label is the PDF's logical label (``"iii"``, ``"365"``)
    and one reader must give one label format.

    Args:
        file: Path to the PDF file.

    Returns:
        ``([(page, page_label, text), ...], tier)`` for the first tier that
        recovers text, or ``([], None)`` when neither does.
    """
    from .registry import get as get_reader

    # Tier 1 — liteparse, constructed extraction-only (design D2: an
    # operator enabling liteparse OCR must not turn the fallback chain
    # into an OCR path); any failure hands over to pypdf (D3).
    try:
        documents = get_reader("liteparse")(ocr_enabled=False, num_workers=None).load_data(file)
        recovered = []
        for index, doc in enumerate(documents):
            page = int(doc.metadata.get("page", index + 1))
            label = str(doc.metadata.get("page_label", page))
            recovered.append((page, label, doc.text or ""))
        recovered = [entry for entry in recovered if entry[2].strip()]
        if recovered:
            return recovered, "liteparse"
    except Exception:  # noqa: BLE001 - a tier failure must never block the next tier
        logger.debug("liteparse fallback tier failed for %s; handing over", file.name)
    # Tier 2 — pypdf: always available; its exceptions propagate to the
    # per-file error boundary (D3) — a file that opens in pdf-inspector
    # but crashes pypdf is genuinely broken input. Number by position
    # first, then drop empty pages, so page 3 stays page 3.
    numbered = [
        (index + 1, str(index + 1), doc.text or "")
        for index, doc in enumerate(get_reader("pypdf")().load_data(file))
    ]
    recovered = [entry for entry in numbered if entry[2].strip()]
    if recovered:
        return recovered, "pypdf"
    return [], None


def _complete_ocr_pages(file: Path, result: Any, scan: Any | None) -> list:
    """Return OCR-needing pages, completing a sampled ``text_based`` result.

    Only a ``text_based`` result on a PDF longer than the detection sample
    can be incomplete: a flagged sample page already makes pdf-inspector
    scan every page, and ``scanned``/``image_based`` PDFs route regardless
    (change full-page-ocr-evidence). Classification, confidence and the
    extracted Markdown stay the library's. The full-scan list comes from
    the per-page result the adapter already fetched for the page text
    (change pdf-inspector-page-provenance, design D1).

    Args:
        file: Path to the PDF file.
        result: The ``process_pdf`` result.
        scan: The ``extract_pages_markdown`` result, or ``None`` when that
            call failed.

    Returns:
        The page list the routing evidence is counted from; the sampled
        list when no full scan is needed or the full scan failed.
    """
    sampled = list(result.pages_needing_ocr or [])
    if result.pdf_type != "text_based" or result.page_count <= PDF_INSPECTOR_SAMPLED_PAGES:
        return sampled
    if scan is None:
        logger.warning(
            "pdf-inspector full page scan failed for %s; keeping the sampled OCR "
            "evidence (%d page(s))",
            file.name,
            len(sampled),
        )
        return sampled
    complete = list(scan.pages_needing_ocr or [])
    if len(complete) > len(sampled):
        logger.info(
            "pdf-inspector full page scan of %s found %d page(s) needing OCR; the "
            "%d-page detection sample found %d",
            file.name,
            len(complete),
            PDF_INSPECTOR_SAMPLED_PAGES,
            len(sampled),
        )
    return complete
