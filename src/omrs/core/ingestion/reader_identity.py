"""PDF reader list in the source index identity (change ordered-reader-and-ocr-lists, D5).

A list that a single ``pdf_reader`` value already means adds nothing to the
identity, so every digest from before the change stays the same. Only a list
that no single value expands to adds ``parser.pdf_readers``. Split out of
``source_state.py``, which sits at the 500-line ceiling.
"""

from __future__ import annotations

from typing import Any

from ..reading_lists import AUTO_READERS, PDF_READERS_DEFAULT, reader_list
from .ocr_identity import non_latin_routing_payload

#: Every list that some single ``pdf_reader`` value expands to (see
#: :func:`omrs.core.reading_lists.expand_pdf_reader`).
_SINGLE_VALUE_LISTS: frozenset[tuple[str, ...]] = frozenset(
    {PDF_READERS_DEFAULT, AUTO_READERS, *((name,) for name in AUTO_READERS)}
)


def reader_list_payload(settings: Any) -> dict[str, list[str]]:
    """Return the ``parser`` entries that the reader list adds for a PDF source.

    Args:
        settings: Injected effective settings.

    Returns:
        ``{}`` when the list equals the expansion of a single value, otherwise
        ``{"pdf_readers": [...]}`` with the full ordered list.
    """
    names = reader_list(settings)
    return {} if names in _SINGLE_VALUE_LISTS else {"pdf_readers": list(names)}


def pdf_parser_payload(settings: Any) -> dict[str, Any]:
    """Return every ``parser`` entry that only a PDF source carries beyond the revision.

    The reader list (D5) and the non-Latin routing block (change
    non-latin-script-routing). Both are empty on a default install.
    """
    return {**reader_list_payload(settings), **non_latin_routing_payload(settings)}
