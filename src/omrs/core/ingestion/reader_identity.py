"""PDF-only ``parser`` entries of the source index identity (ordered-reader-and-ocr-lists D5).

A list that a single ``pdf_reader`` value already means adds nothing to the
identity, so every digest from before the change stays the same. Only a list
that no single value expands to adds ``parser.pdf_readers``. Split out of
``source_state.py``, which sits at the 500-line ceiling.
"""

from __future__ import annotations

from typing import Any

from ..reading_lists import AUTO_READERS, PDF_READERS_DEFAULT, reader_list
from ..reading_parts import (
    KIND_LOCAL_OCR_BACKEND,
    KIND_PAGE_RULE,
    KIND_PDF_READER,
    RULE_ENABLED_OPTION,
    SOURCE_BUILT_IN,
    PartDescriptor,
    parts_named,
)
from .ocr_identity import local_backends_payload, non_latin_routing_payload

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


def _rule_enabled(part: PartDescriptor, values: dict[str, Any], settings: Any) -> bool:
    return part.source != SOURCE_BUILT_IN and values.get(RULE_ENABLED_OPTION.name) is True


#: Part kind to the test of whether a part of that kind reads this source.
_IN_USE = {
    KIND_PAGE_RULE: _rule_enabled,
    KIND_LOCAL_OCR_BACKEND: lambda part, _values, settings: (
        part.name in tuple(getattr(settings, "ocr_local_backends", ()))
    ),
    KIND_PDF_READER: lambda part, _values, settings: part.name in reader_list(settings),
}


def part_options_payload(settings: Any) -> dict[str, Any]:
    """Return the ``parser`` entry of the part options that change the text (design D12).

    Only a part in use counts: a listed reader or backend, or a discovered page
    rule with ``enabled`` true (which enters as ``enabled``). Of its options,
    only those the descriptor marks ``enters_identity`` and the map sets enter.
    An empty map, or one that only switches built-in parts, adds nothing.

    Args:
        settings: Injected settings carrying ``reading_part_options``.

    Returns:
        ``{}`` or ``{"reading_part_options": {part: {key: value}}}``.
    """
    options = getattr(settings, "reading_part_options", None) or {}
    chosen: dict[str, dict[str, Any]] = {}
    for name in sorted(options):
        values = options[name]
        entry: dict[str, Any] = {}
        for part in parts_named(name):
            if not _IN_USE[part.kind](part, values, settings):
                continue
            if part.kind == KIND_PAGE_RULE:
                entry[RULE_ENABLED_OPTION.name] = True
            entry.update(
                (o.name, values[o.name])
                for o in part.options
                if o.enters_identity and o.name in values
            )
        if entry:
            chosen[name] = dict(sorted(entry.items()))
    return {"reading_part_options": chosen} if chosen else {}


def pdf_parser_payload(settings: Any) -> dict[str, Any]:
    """Return every ``parser`` entry that only a PDF source carries beyond the revision.

    The reader list (D5), the non-Latin routing block (change
    non-latin-script-routing), the local OCR backend list and the part options
    (change local-ocr-backends). All four are empty on a default install.
    """
    return {
        **reader_list_payload(settings),
        **non_latin_routing_payload(settings),
        **local_backends_payload(settings),
        **part_options_payload(settings),
    }
