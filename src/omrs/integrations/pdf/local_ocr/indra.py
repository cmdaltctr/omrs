"""The ``indra`` local OCR backend: Indra OCR 1.1.2 on ONNX Runtime (design D19).

``read_pages`` repeats the Experiment 46 call (``run_arm.py``, arm B): one
``OrtOCR`` with default threads, one grey page image per call, the page's lines in
reading order. Experiment 46 read PNG files 1600 px on the long side, so each page
is rendered at that size. The renderer is ``pypdfium2``, a dependency of
``indra-ocr`` and the renderer the library itself uses for PDF files.

The text is the lines joined with newlines. The page confidence is the
character-weighted mean of the line confidences (:func:`.base.page_confidence`).

The weights come from ``indra_ocr.model_dir()``: the ``INDRA_OCR_MODEL_DIR``
folder when it is set, else the Hugging Face cache, else a download. Under
``ocr_local_offline`` the backend reads only the ``INDRA_OCR_MODEL_DIR`` folder,
so it never downloads. ``identity`` gives the model only when those weights are
already on disk, and it never downloads either.

``indra_ocr`` and ``pypdfium2`` are imported inside each method, because tests
stub them in ``sys.modules`` after this module is imported.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .base import BackendPage, page_confidence

#: The model the cut was measured with: Hugging Face snapshot of tag v1.1.0.
MODEL = "datalab-to/indra-ocr@bd02167fdf2005a19962cc15188f8496a2c87d3b"

#: The long side of a rendered page, as in the Experiment 46 page images.
LONG_SIDE_PX = 1600


def _require() -> Any:
    """Import ``indra_ocr``, with a message that names the extra."""
    try:
        import indra_ocr
    except ImportError as exc:
        raise ImportError(
            "indra_ocr is not installed. Install with: uv sync --extra local-ocr-indra"
        ) from exc
    return indra_ocr


def _render(file: Path, pages: list[int]) -> Iterator[tuple[int, Any]]:
    """Yield ``(page, grey image)`` for each 1-based page, long side 1600 px."""
    import numpy as np
    import pypdfium2

    document = pypdfium2.PdfDocument(str(file))
    try:
        for number in pages:
            page = document[number - 1]
            scale = LONG_SIDE_PX / max(page.get_size())
            image = page.render(scale=scale, grayscale=True).to_numpy()
            yield number, np.ascontiguousarray(image[..., 0] if image.ndim == 3 else image)
    finally:
        document.close()


class IndraOcr:
    """Indra OCR through ``indra_ocr.OrtOCR``, one model per weights folder."""

    def __init__(self) -> None:
        self._engines: dict[str, Any] = {}

    def _engine(self, indra_ocr: Any, settings: Any) -> Any:
        """Return the loaded model of the current weights folder, loading it once.

        Raises:
            RuntimeError: ``ocr_local_offline`` is set and ``INDRA_OCR_MODEL_DIR``
                is not, so finding the weights could download them.
        """
        if getattr(settings, "ocr_local_offline", False) and not os.environ.get(
            "INDRA_OCR_MODEL_DIR"
        ):
            raise RuntimeError(
                "Local OCR is offline, so Indra reads its weights only from the "
                "INDRA_OCR_MODEL_DIR folder. Set INDRA_OCR_MODEL_DIR."
            )
        folder = indra_ocr.model_dir()
        key = str(folder)
        if key not in self._engines:
            self._engines[key] = indra_ocr.OrtOCR(folder)
        return self._engines[key]

    def read_pages(self, file: Path, pages: list[int], *, settings: Any) -> list[BackendPage]:
        """OCR *pages* of *file*, one rendered page image at a time.

        Args:
            file: Path to the PDF file.
            pages: 1-based page numbers.
            settings: Injected settings; Indra reads ``ocr_local_offline``.

        Returns:
            One :class:`BackendPage` per page, in page order.

        Raises:
            ImportError: ``indra_ocr`` is not installed.
            RuntimeError: Offline with no ``INDRA_OCR_MODEL_DIR`` folder.
            Exception: The weights are missing, or rendering or the engine fails.
        """
        engine = self._engine(_require(), settings)
        read: list[BackendPage] = []
        for number, image in _render(file, sorted(pages)):
            lines = [(line.text, float(line.conf)) for line in engine(image).lines]
            read.append(
                BackendPage(
                    page=number,
                    text="\n".join(text for text, _ in lines),
                    confidence=page_confidence(lines),
                    model=MODEL,
                )
            )
        return read

    def identity(self, settings: Any) -> str | None:
        """Return the pinned model identity when the weights can load, else ``None``.

        The weights must be on disk: the ``INDRA_OCR_MODEL_DIR`` folder when it
        is set, else the Hugging Face cache. Offline, only that folder counts, as
        in :meth:`read_pages`. The check never downloads.

        Raises:
            ImportError: ``indra_ocr`` is not installed.
        """
        return MODEL if _weights_present(_require(), settings) else None


def _has_weights(folder: Path, indra_ocr: Any) -> bool:
    """Return whether *folder* holds every file ``indra_ocr.model_dir`` requires.

    As the library does, ``order.onnx`` is optional (reading order then falls
    back to XY-cut).
    """
    required = [name for name in indra_ocr.models.FILES if name != "order.onnx"]
    return all((folder / name).is_file() for name in required)


def _weights_present(indra_ocr: Any, settings: Any) -> bool:
    """Return whether the weights are on disk, without a download."""
    folder = os.environ.get("INDRA_OCR_MODEL_DIR")
    if folder:
        return _has_weights(Path(folder).expanduser(), indra_ocr)
    if getattr(settings, "ocr_local_offline", False):
        return False
    models = indra_ocr.models
    try:
        from huggingface_hub import snapshot_download

        cached = snapshot_download(
            models.HF_REPO, revision=models.HF_REVISION, local_files_only=True
        )
    except Exception:  # noqa: BLE001 - not cached, or no hub: the weights cannot load
        return False
    return _has_weights(Path(cached), indra_ocr)


#: The backend object the registry loads.
BACKEND = IndraOcr()
