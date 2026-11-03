"""Maths-page routing decisions for the pdf-inspector seam (design D6).

``ocr_routing.py`` sits near the 500-line ceiling, so the decisions live
here and the seam calls them:

- :func:`detect_maths_pages` runs the font detector once per PDF, only
  when maths routing is enabled;
- :func:`split_page_routes` is the page-unit split: maths pages skip the
  local OCR tier and join the escalated pages in the one page-listed
  request to the OCR routes.

Every value comes from the injected settings. The document-unit maths
condition went with the document unit (change page-routing-default).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .maths_pages import maths_font_pages

#: Scalar diagnostic: the number of flagged maths pages. It is excluded
#: from embedded text (``EXCLUDED_EMBED_METADATA_KEYS``).
PAGES_MATHS_FONT_KEY = "pages_maths_font"


def maths_routing_enabled(settings: Any) -> bool:
    """Return the injected maths-routing flag."""
    return bool(getattr(settings, "ocr_maths_routing_enabled", False))


def detect_maths_pages(file: Path | str, settings: Any) -> frozenset[int] | None:
    """Return the flagged maths pages, or ``None`` when routing is disabled.

    ``None`` (not an empty set) marks "not detected", so the caller emits
    no ``pages_maths_font`` key and routing behaves as before.
    """
    if not maths_routing_enabled(settings):
        return None
    return maths_font_pages(file)


def split_page_routes(
    flagged: Iterable[int], maths_pages: frozenset[int] | None
) -> tuple[frozenset[int], list[int]]:
    """Split page-unit work between the OCR routes and the local tier.

    Args:
        flagged: Pages the full scan flagged as needing OCR.
        maths_pages: Flagged maths pages, or ``None`` when disabled.

    Returns:
        ``(direct, local)``: maths pages that go straight to the OCR
        routes, and the sorted pages the local tier reads. A page that
        is both a maths page and flagged goes direct, once.
    """
    direct = frozenset(maths_pages or ())
    local = sorted(set(flagged) - direct)
    return direct, local


def stamp_maths_count(metadata: dict[str, Any], maths_pages: frozenset[int] | None) -> None:
    """Stamp ``pages_maths_font`` when maths routing ran."""
    if maths_pages is not None:
        metadata[PAGES_MATHS_FONT_KEY] = len(maths_pages)
