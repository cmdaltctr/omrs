"""The ``pp-ocrv6-small`` local OCR backend: pdf-inspector's selective OCR (design D7).

``read_pages`` is the call Experiment 33 task 6.7 measured: ``force`` mode on the
1-based page list, so the library re-routes nothing. The model directory and the
offline mode come from the injected settings; an empty directory means the
library's default cache. The engine's own ``minimum_confidence`` and
``hosted_recommendation_confidence`` stay at the library defaults: the cut is
applied after the read, by the chain.

``pdf_inspector`` is imported inside each method, because tests stub
``sys.modules["pdf_inspector"]`` after this module is imported.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from .base import BackendPage


def _model_identity(provenance: Any) -> str | None:
    """Return ``name@revision`` from a page's provenance, or ``None``."""
    model = getattr(provenance, "ocr_model", None)
    if model is None:
        return None
    return f"{model.name}@{model.revision}"


def _model_options(settings: Any) -> dict[str, Any]:
    return {
        "model_directory": (settings.ocr_local_model_directory or None),
        "offline": bool(settings.ocr_local_offline),
    }


class PpOcrV6Small:
    """PP-OCRv6 small through ``pdf_inspector.process_pdf_with_ocr``."""

    def read_pages(self, file: Path, pages: list[int], *, settings: Any) -> list[BackendPage]:
        """OCR *pages* of *file* in one ``force`` call.

        Args:
            file: Path to the PDF file.
            pages: 1-based page numbers.
            settings: Injected settings carrying ``ocr_local_model_directory``
                and ``ocr_local_offline``.

        Returns:
            One :class:`BackendPage` per page the library returned.

        Raises:
            ImportError: ``pdf_inspector`` is not installed.
            Exception: The engine raises.
        """
        try:
            import pdf_inspector
        except ImportError as exc:  # mirrors the adapter's message
            raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

        result = pdf_inspector.process_pdf_with_ocr(
            str(file), mode="force", page_numbers=sorted(pages), **_model_options(settings)
        )
        read: list[BackendPage] = []
        for page in result.pages:
            provenance = getattr(page, "provenance", None)
            read.append(
                BackendPage(
                    page=page.page_number,
                    text=getattr(page, "markdown", "") or "",
                    confidence=getattr(provenance, "ocr_confidence", None),
                    model=_model_identity(provenance),
                    hosted_recommended=bool(getattr(provenance, "hosted_recommended", False)),
                )
            )
        return read

    def identity(self, settings: Any) -> str | None:
        """Resolve the model's ``name@revision`` with a one-page blank probe.

        pdf-inspector reports the identity only in per-page provenance after an
        OCR run, and an empty page list skips the model, so the probe is a
        one-page ``force`` attempt on a generated blank PDF. The blank page costs
        one render and no recognition work.

        Raises:
            ImportError: ``pdf_inspector`` or ``pypdf`` is not installed.
            Exception: The engine raises.
        """
        import pdf_inspector
        from pypdf import PdfWriter

        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                path = handle.name
                writer = PdfWriter()
                writer.add_blank_page(width=200, height=200)
                writer.write(path)
            result = pdf_inspector.process_pdf_with_ocr(
                path, mode="force", page_numbers=[1], **_model_options(settings)
            )
            for page in result.pages:
                identity = _model_identity(getattr(page, "provenance", None))
                if identity is not None:
                    return identity
            return None
        finally:
            if path is not None:
                try:
                    os.unlink(path)
                except OSError:  # pragma: no cover - best-effort temp cleanup
                    pass


#: The backend object the registry loads.
BACKEND = PpOcrV6Small()
