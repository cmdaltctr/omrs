"""Blank-page detection from page-image ink (change skip-blank-pages-before-worker).

A flagged page whose image carries no stroke ink is a blank sheet: a
cover, an empty back, the bed of a scanner. Sending it to local OCR and
then to the OCR engine buys 33 to 51 s of engine time for text nobody
can read off the page (handoff 2026-11-02, "rf06 unresolved pages").
This module answers one question before any OCR tier runs: is this page
blank?

The signal is edge-free stroke ink (design.md, "The chosen signal"):

1. render the page, convert to grey, downscale so the long side is
   1000 px (a box filter, so the score barely follows render dpi);
2. close with a 9 x 9 square (maximum, then minimum) — thin dark
   strokes vanish in the closed image, large dark areas and straight
   sheet edges survive;
3. stroke ink: pixels where the closing is brighter than the image by
   more than 40 grey levels;
4. drop specks: an ink pixel survives only with at least 3 ink
   neighbours of 8 (scanned paper grain and dust die here);
5. drop every ink mark connected to the image border (scanner frames
   and the edge of a small sheet);
6. score: the fraction of pixels still ink. Below
   :data:`BLANK_PAGE_INK_THRESHOLD` the page is blank.

Measured on all 1,123 Experiment 33 pages: no page with 3 or more
reference characters, and no illegible page, scores below the threshold;
the lowest content page sits 5.3 times above it. The test reads the
page image and never OCR text, because local OCR also returns empty on
real content (recall 0.000 on Arabic and Devanagari, Experiment 33).

Failure is cheap: a page that cannot be rendered or scored is not
blank, one warning names the file, and the page follows today's route.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Bump on ANY change to the score or the threshold. The version joins
#: the page-unit source index identity, so a change re-ingests page-unit
#: sources only. A test pins the value.
BLANK_PAGE_TEST_VERSION = 1

#: A page is blank below this fraction of remaining ink pixels. Calibrated
#: 2026-11-02 on all 1,123 Experiment 33 pages: 1.6 times the highest
#: blank page, 5.3 times below the lowest page with content. A test pins
#: the value.
BLANK_PAGE_INK_THRESHOLD = 1.5e-4

#: Renders go to LiteParse in batches, because one page PNG is up to
#: 1.5 MB and a scan can flag hundreds of pages (design decision 2).
_RENDER_BATCH = 16

#: The score works at this long side, whatever the render dpi.
_LONG_SIDE_PX = 1000

#: Closing kernel (odd) and the grey-level depth a stroke must show.
_CLOSING_SIZE = 9
_CLOSING_DEPTH = 40

#: An ink pixel survives speck removal with at least this many ink
#: neighbours of 8.
_SPECK_NEIGHBOURS = 3

#: The eight neighbour offsets, shared by speck removal and the
#: border-connected flood.
_DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def score_is_blank(score: float) -> bool:
    """Return whether *score* is below the blank threshold."""
    return score < BLANK_PAGE_INK_THRESHOLD


def page_ink_score(image: Any) -> float:
    """Return the edge-free stroke-ink fraction of a page image.

    Args:
        image: The rendered page, any PIL mode (converted to grey here).

    Returns:
        The fraction of pixels that stay ink after closing, speck
        removal and border-connected removal. ``0.0`` for a page with no
        surviving ink.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    grey = image.convert("L")
    if max(grey.size) > _LONG_SIDE_PX:
        scale = _LONG_SIDE_PX / max(grey.size)
        size = (round(grey.width * scale), round(grey.height * scale))
        grey = grey.resize(size, Image.Resampling.BOX)
    closed = grey.filter(ImageFilter.MaxFilter(_CLOSING_SIZE)).filter(
        ImageFilter.MinFilter(_CLOSING_SIZE)
    )
    plain = np.asarray(grey, dtype=np.int16)
    filled = np.asarray(closed, dtype=np.int16)
    ink = (filled - plain) > _CLOSING_DEPTH
    ink = _without_specks(ink)
    ink = _without_border_connected(ink)
    return float(int(ink.sum()) / ink.size) if ink.size else 0.0


def find_blank_pages(file: Path | str, pages: Sequence[int]) -> frozenset[int]:
    """Return the blank subset of *pages* in *file*, or none on any failure.

    Renders through LiteParse in batches of 16 and scores each page with
    :func:`page_ink_score`. A page the renderer never returned, or whose
    image fails to decode or score, is not blank. A render failure
    disables the whole call: one warning names the file and every page
    keeps today's route (design decision 4 — the file never fails because
    of the test).

    Args:
        file: Path to the PDF.
        pages: 1-based page numbers, any order; duplicates are rendered once.

    Returns:
        The blank pages among *pages*.
    """
    wanted = sorted(set(pages))
    if not wanted:
        return frozenset()
    try:
        return _blank_pages_in_batches(file, wanted)
    except Exception as exc:  # noqa: BLE001 - a failed test must not fail the file
        logger.warning(
            "Blank-page test unavailable for %s (%s: %s); flagged pages "
            "follow their normal OCR route",
            getattr(file, "name", file),
            type(exc).__name__,
            exc,
        )
        return frozenset()


def _blank_pages_in_batches(file: Path | str, wanted: list[int]) -> frozenset[int]:
    """Render and score page by page, batch by batch, keeping only numbers."""
    from liteparse import LiteParse

    parser = LiteParse(ocr_enabled=False, quiet=True)
    blank: set[int] = set()
    for start in range(0, len(wanted), _RENDER_BATCH):
        batch = wanted[start : start + _RENDER_BATCH]
        for shot in parser.screenshot(str(file), page_numbers=batch):
            image = _decode(shot.image_bytes)
            if image is None:
                continue
            try:
                score = page_ink_score(image)
            except Exception as exc:  # noqa: BLE001 - one unreadable page is not blank
                logger.debug(
                    "blank-page score failed for page %s of %s (%s: %s); page not blank",
                    shot.page_num,
                    getattr(file, "name", file),
                    type(exc).__name__,
                    exc,
                )
                continue
            if score_is_blank(score):
                blank.add(int(shot.page_num))
    return frozenset(blank)


def _decode(data: bytes) -> Any:
    """Decode one PNG payload, or return ``None`` when it is unusable."""
    from PIL import Image

    try:
        with Image.open(BytesIO(data)) as handle:
            return handle.copy()
    except Exception:  # noqa: BLE001 - a bad payload is one page, not one file
        logger.debug("blank-page render payload failed to decode; page not blank")
        return None


def _neighbour_sums(mask: Any) -> Any:
    """Count, per pixel, how many of its 8 neighbours are set in *mask*."""
    import numpy as np

    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), dtype=np.uint8)
    for dy, dx in _DIRECTIONS:
        padded[1 + dy : 1 + dy + mask.shape[0], 1 + dx : 1 + dx + mask.shape[1]] += mask
    return padded[1:-1, 1:-1]


def _without_specks(ink: Any) -> Any:
    """Drop ink pixels with fewer than :data:`_SPECK_NEIGHBOURS` ink neighbours."""
    import numpy as np

    return ink & (_neighbour_sums(ink.astype(np.uint8)) >= _SPECK_NEIGHBOURS)


def _without_border_connected(ink: Any) -> Any:
    """Drop every ink mark reachable from the image border through ink.

    Geodesic reconstruction from the border: dilate the border seed
    inside the ink mask until nothing new is reached. Scanner frames and
    the edge of a small sheet die here; a header near the top edge, not
    touching it, survives.
    """
    import numpy as np

    seed = np.zeros_like(ink)
    seed[0, :] = ink[0, :]
    seed[-1, :] = ink[-1, :]
    seed[:, 0] = ink[:, 0]
    seed[:, -1] = ink[:, -1]
    if not seed.any():
        return ink
    reached = seed
    while True:
        grown = ((_neighbour_sums(reached.astype(np.uint8)) > 0) & ink) | reached
        if np.array_equal(grown, reached):
            return ink & ~reached
        reached = grown
