"""pypdfium2 page renderer, second in the list (design D5).

It is available when the optional ``pdf-pypdfium2`` extra is installed.
pypdfium2 numbers pages from 0, so page ``n`` is index ``n - 1``.
"""

from __future__ import annotations

import io
from pathlib import Path

#: PDF user-space units per inch.
_POINTS_PER_INCH = 72


class PyPdfium2Renderer:
    """Render one page with pypdfium2 and encode it as PNG."""

    def render(self, file: Path, page: int, dpi: float) -> tuple[bytes, tuple[int, int]]:
        """Render *page* of *file* at *dpi*.

        Args:
            file: Path to the PDF file.
            page: Page number, from 1.
            dpi: Resolution in dots per inch.

        Returns:
            The PNG bytes and the image ``(width, height)`` in pixels.
        """
        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(file))
        try:
            image = pdf[page - 1].render(scale=dpi / _POINTS_PER_INCH).to_pil()
        finally:
            pdf.close()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), image.size


#: The renderer object the registry loads.
RENDERER = PyPdfium2Renderer()
