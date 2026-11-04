"""Reader list rules: start-up choice and the pdf-inspector rescue chain.

Change ordered-reader-and-ocr-lists, design D2 and D3.

Start-up (:func:`clean_reader_list`, :func:`first_installed`): the first
installed reader of the list reads the file.

Rescue (:func:`rescue_pages`): pdf-inspector may classify a PDF as
``text_based`` and still extract nothing (TDR-024). The readers listed after
it then read the file again, in list order, in extraction-only mode
(ADR-066). This module names no reader: tier names come from the caller and
each tier is built through the registry, so a new reader needs one adapter
file and one ``register()`` line.

The rule for "the next reader" (design D2): a tier that is not installed,
raises or returns no text hands over to the next tier. The last tier's
exception propagates, because it means broken input.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The tiers of a ``PdfInspectorReader`` built without a reader list: the
#: ADR-066 chain, LiteParse first and pypdf last.
DEFAULT_TIERS: tuple[str, ...] = ("liteparse", "pypdf")

#: Constructor options a tier receives when it accepts them. A rescue tier
#: must not become an OCR path, whatever the operator enabled (ADR-066).
_EXTRACTION_ONLY: dict[str, Any] = {"ocr_enabled": False, "num_workers": None}


def clean_reader_list(names: Sequence[str]) -> tuple[str, ...]:
    """Drop the names a list may not hold, with a warning for each.

    ``auto`` is a single-value policy, and an unregistered name is no reader.
    Installed state is not tested here: a listed reader that is not installed
    stays in the list and is skipped at start-up by :func:`first_installed`.

    Args:
        names: The reader list from the settings.

    Returns:
        The registered, concrete names in their original order.
    """
    from . import registry

    registered = set(registry.available())
    kept: list[str] = []
    for name in names:
        if name == "auto":
            logger.warning("PDF reader 'auto' is a single-value policy; dropping it from the list.")
        elif name not in registered:
            logger.warning("PDF reader %r is unregistered; dropping it from the list.", name)
        else:
            kept.append(name)
    return tuple(kept)


def first_installed(names: Sequence[str]) -> str:
    """Return the first reader of *names* whose package imports.

    Each reader skipped on the way is named in an error. When none is
    installed the result is ``pypdf``, the base dependency.

    Args:
        names: Registered reader names from :func:`clean_reader_list`.

    Returns:
        The reader that reads the file.
    """
    from . import registry

    missing: list[str] = []
    for name in names:
        try:
            registry.probe(name)
        except ImportError:
            missing.append(name)
            continue
        if missing:
            logger.error("PDF reader(s) %s not installed. Using %r instead.", missing, name)
        return name
    logger.error("PDF reader(s) %s not installed. Falling back to pypdf.", missing)
    return "pypdf"


def construct(reader_class: type[Any], **options: Any) -> Any:
    """Build *reader_class* with the *options* its constructor accepts.

    A reader that takes none of them is built bare. This keeps tier and
    extraction-only options out of the adapters that have no use for them,
    with no branch on reader names.
    """
    accepted = inspect.signature(reader_class).parameters
    return reader_class(**{key: value for key, value in options.items() if key in accepted})


def tiers_after(primary: str, readers: Sequence[str]) -> tuple[str, ...]:
    """Return the readers that follow *primary* in *readers*.

    Args:
        primary: The reader that reads the file first.
        readers: The ordered reader list.

    Returns:
        The names after *primary*, or an empty tuple when *primary* is not
        in the list or is its last entry.
    """
    names = tuple(readers)
    return names[names.index(primary) + 1 :] if primary in names else ()


def rescue_pages(file: Path, tiers: Sequence[str]) -> tuple[list[tuple[int, str, str]], str | None]:
    """Read *file* with each tier in turn and keep one entry per recovered page.

    Each recovered page stays its own document (change
    pdf-inspector-page-provenance, design D4). A tier that reports a physical
    ``page`` keeps it. A tier without one is numbered by position, counted
    before empty pages are dropped, because its own label is the PDF's logical
    label (``"iii"``, ``"365"``) and one reader must give one label format.

    Args:
        file: Path to the PDF file.
        tiers: Registered reader names, tried in order.

    Returns:
        ``([(page, page_label, text), ...], tier)`` for the first tier that
        recovers text, or ``([], None)`` when none does.

    Raises:
        Exception: Whatever the last tier raises while reading. A file that
            opens in pdf-inspector but crashes the last tier is broken input
            for the per-file error boundary.
    """
    for position, name in enumerate(tiers):
        try:
            reader = _build_tier(name)
        except Exception:  # noqa: BLE001 - an unavailable tier must never block the next one
            logger.debug("%s fallback tier is unavailable for %s; handing over", name, file.name)
            continue
        try:
            documents = reader.load_data(file)
        except Exception:  # noqa: BLE001 - only the last tier may fail the read
            if position == len(tiers) - 1:
                raise
            logger.debug("%s fallback tier failed for %s; handing over", name, file.name)
            continue
        recovered = _numbered_pages(documents)
        if recovered:
            return recovered, name
    return [], None


def _build_tier(name: str) -> Any:
    """Construct the registered reader *name*, extraction-only where it has the options.

    Raises:
        ImportError: The reader's package is not installed. The probe runs
            first because most adapters import their package inside
            ``load_data``, which would turn "not installed" into a tier crash.
    """
    from . import registry

    registry.probe(name)
    return construct(registry.get(name), **_EXTRACTION_ONLY)


def _numbered_pages(documents: Sequence[Any]) -> list[tuple[int, str, str]]:
    """Return ``(page, label, text)`` for each document with text, numbered 1-based."""
    pages = [
        (int(doc.metadata.get("page", index + 1)), doc.text or "")
        for index, doc in enumerate(documents)
    ]
    return [(page, str(page), text) for page, text in pages if text.strip()]
