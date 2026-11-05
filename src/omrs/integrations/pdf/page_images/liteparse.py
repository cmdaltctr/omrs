"""LiteParse page renderer, the first of the list (design D5).

LiteParse is a base dependency, so image routers work on a default install.
Its ``screenshot`` call numbers pages from 1, as the page scan does.
"""

from __future__ import annotations

from pathlib import Path


class LiteParseRenderer:
    """Render one page with LiteParse ``screenshot``."""

    def render(self, file: Path, page: int, dpi: float) -> tuple[bytes, tuple[int, int]]:
        """Render *page* of *file* at *dpi*.

        Args:
            file: Path to the PDF file.
            page: Page number, from 1.
            dpi: Resolution in dots per inch.

        Returns:
            The PNG bytes and the image ``(width, height)`` in pixels.

        Raises:
            ValueError: If LiteParse returns no image for the page.
        """
        from liteparse import LiteParse

        results = LiteParse(quiet=True, dpi=dpi).screenshot(file, page_numbers=[page])
        for result in results:
            if result.page_num == page:
                return result.image_bytes, (result.width, result.height)
        raise ValueError(f"LiteParse returned no image for page {page}")


#: The renderer object the registry loads.
RENDERER = LiteParseRenderer()
