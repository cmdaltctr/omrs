"""Non-Latin page routing for the page unit (change non-latin-script-routing).

``ocr_non_latin_routing`` has three values:

- ``off`` (default): nothing here runs.
- ``detect``: a flagged page whose text layer is mostly non-Latin letters skips
  the local OCR tier, and a local OCR result that is mostly non-Latin letters
  escalates whatever its confidence.
- ``always``: every flagged page skips the local tier.

The detector reads text that already exists. It never renders a page, runs OCR
or calls a model. A scanned page has no text layer, so ``detect`` cannot see it
before OCR; ``always`` is the only way to skip the local tier for scans.

The letter floor and the share are fixed here with a version number (design
D2). They are not settings. The version joins the source index identity.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Collection, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..ocr_worker.protocol import PAGES_PROTOCOL_VERSION
from ..ocr_worker.routes import engine_names

logger = logging.getLogger(__name__)

#: Bump on ANY change to :data:`MIN_LETTERS` or :data:`NON_LATIN_SHARE`. The
#: version joins the source index identity, so a change re-ingests. A test pins
#: both constants to this version.
SCRIPT_DETECTOR_VERSION = 1

#: Fewest letters a text needs before the detector gives a verdict. A scan's
#: stamp or catalogue text holds about 7 letters (Experiment 33 probe).
MIN_LETTERS = 40

#: The text is non-Latin when at least this share of its letters is not Latin.
NON_LATIN_SHARE = 0.5

#: Scalar diagnostic: pages this setting sent direct or escalated. Excluded
#: from embedded text (``EXCLUDED_EMBED_METADATA_KEYS``).
PAGES_NON_LATIN_KEY = "pages_non_latin"

#: The escalation reason the post-local check adds.
NON_LATIN_OUTPUT_REASON = "non_latin_output"


@lru_cache(maxsize=4096)
def _is_latin_letter(char: str) -> bool:
    return unicodedata.name(char, "").startswith("LATIN")


def is_non_latin(text: str) -> bool | None:
    """Return whether *text* is mostly non-Latin letters, or ``None`` for no verdict.

    Args:
        text: Page text. Digits, punctuation and space are not letters.

    Returns:
        ``None`` when the text holds fewer than :data:`MIN_LETTERS` letters,
        else ``True`` when at least :data:`NON_LATIN_SHARE` of the letters are
        not Latin, else ``False``. A Latin letter has a Unicode name that
        starts with ``LATIN``, so accented Latin letters count as Latin.
    """
    letters = [char for char in text if char.isalpha()]
    if len(letters) < MIN_LETTERS:
        return None
    other = sum(1 for char in letters if not _is_latin_letter(char))
    return other / len(letters) >= NON_LATIN_SHARE


def routing_mode(settings: Any) -> str:
    """Return the injected mode: ``off``, ``detect`` or ``always``."""
    return str(getattr(settings, "ocr_non_latin_routing", "off") or "off")


def _engine_available(routes: Any) -> bool:
    return routes.select(protocol=PAGES_PROTOCOL_VERSION) is not None


def post_check_enabled(settings: Any, routes: Any) -> bool:
    """Return whether the post-local check runs: ``detect`` with an engine to escalate to."""
    return routing_mode(settings) == "detect" and _engine_available(routes)


def non_latin_output_reason(text: str, facts: Any = None) -> str | None:
    """Return :data:`NON_LATIN_OUTPUT_REASON` when a local result is mostly non-Latin.

    The post-local check (a page-rule post-check). *facts* are the facts of the
    backend that read the page; this check does not read them yet.
    """
    return NON_LATIN_OUTPUT_REASON if is_non_latin(text) is True else None


def _text_layer_verdicts(file: Path, pages: Collection[int]) -> frozenset[int]:
    """Return the *pages* whose text items are mostly non-Latin letters.

    One ``extract_text_with_positions`` call per file, for the flagged pages
    only. Both its page argument and ``TextItem.page`` count from 1. A failed
    call finds no page, so the file keeps today's routing.
    """
    try:
        import pdf_inspector

        items = pdf_inspector.extract_text_with_positions(str(file), sorted(pages))
    except Exception as exc:  # noqa: BLE001 - a heuristic must not fail the file
        logger.warning("Non-Latin check skipped for %s: %s", getattr(file, "name", file), exc)
        return frozenset()
    by_page: dict[int, list[str]] = {}
    for item in items:
        by_page.setdefault(item.page, []).append(item.text)
    return frozenset(
        page for page in pages if is_non_latin(" ".join(by_page.get(page, ()))) is True
    )


def non_latin_direct_pages(
    file: Path, routed: Iterable[int], settings: Any, routes: Any
) -> frozenset[int]:
    """Return the routed pages that skip the local tier because of this setting.

    Args:
        file: Path to the PDF file.
        routed: Flagged pages that are not blank.
        settings: Injected settings carrying ``ocr_non_latin_routing``.
        routes: The injected ``OcrRoutes``.

    Returns:
        ``frozenset()`` when the mode is ``off`` or when no OCR engine that
        speaks the page-listed protocol is available (design D5; one warning
        names the engines). Otherwise every routed page under ``always``, or
        the routed pages with a non-Latin text layer under ``detect``.
    """
    mode = routing_mode(settings)
    pages = frozenset(routed)
    if mode == "off" or not pages:
        return frozenset()
    chosen = pages if mode == "always" else _text_layer_verdicts(file, pages)
    if chosen and not _engine_available(routes):
        logger.warning(
            "Non-Latin routing is %s but no OCR engine that speaks protocol %s is available "
            "for %s (engines: %s); %d page(s) go through the local tier as before.",
            mode,
            PAGES_PROTOCOL_VERSION,
            getattr(file, "name", file),
            ", ".join(engine_names(settings)) or "none configured",
            len(chosen),
        )
        return frozenset()
    return chosen


def stamp_non_latin_count(
    metadata: dict[str, Any], settings: Any, direct: Collection[int], escalated: Iterable[Any]
) -> None:
    """Stamp ``pages_non_latin`` when the setting is not ``off``.

    Counts the pages this setting chose to send direct, plus the local results
    escalated with the reason ``non_latin_output``. A page that is also a
    maths page counts here too. A page with no verdict is never counted.

    Args:
        metadata: Document metadata to stamp.
        settings: Injected settings.
        direct: Pages from :func:`non_latin_direct_pages`.
        escalated: The local results (``LocalOcrPage``, or ``None`` for a page
            that had none) of the pages that escalated.
    """
    if routing_mode(settings) == "off":
        return
    by_output = sum(
        1 for page in escalated if page is not None and NON_LATIN_OUTPUT_REASON in page.reasons
    )
    metadata[PAGES_NON_LATIN_KEY] = len(direct) + by_output
