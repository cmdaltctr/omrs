"""Ordered PDF reader and OCR engine lists: defaults, parsing and expansion.

Pure data and pure functions (change ordered-reader-and-ocr-lists, design D4).
``config`` and the readers of ``EffectiveSettings`` both import it, so the old
single-value keys (``pdf_reader``, ``ocr_engine_primary``, ``ocr_engine_fallback``)
and the new list keys (``pdf_readers``, ``ocr_engines``) expand by one rule.
``core/settings.py`` cannot import it (that module imports nothing from ``core``).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_settings import NoDecode

#: The ADR-066 rescue chain written out: pdf-inspector first, then the two
#: rescue tiers. Equals :func:`expand_pdf_reader` of the default ``pdf_inspector``.
PDF_READERS_DEFAULT: tuple[str, ...] = ("pdf_inspector", "liteparse", "pypdf")
#: Primary engine, then fallback. Equals :func:`expand_ocr_engines` of the defaults.
OCR_ENGINES_DEFAULT: tuple[str, ...] = ("dots-mocr", "paddleocr-vl")
#: What ``pdf_reader=auto`` has always tried: the first one installed wins.
AUTO_READERS: tuple[str, ...] = ("liteparse", "pypdfium2", "pypdf")


def parse_name_list(value: Any) -> Any:
    """Parse the environment form (``a, b``) or the file form (a JSON array) of a name list.

    Text is split on commas. Padding is trimmed and empty items are dropped.
    A list or tuple is trimmed item by item. Items that are not text are left
    for pydantic to refuse. Any other value passes through.
    """
    if isinstance(value, str):
        value = value.split(",")
    if isinstance(value, (list, tuple)):
        items = (item.strip() if isinstance(item, str) else item for item in value)
        return tuple(item for item in items if item != "")
    return value


#: ``NoDecode`` stops pydantic-settings from reading the environment value as
#: JSON, so ``PDF_READERS=pdf_inspector,pypdf`` reaches :func:`parse_name_list`.
NameList = Annotated[tuple[str, ...], NoDecode, BeforeValidator(parse_name_list)]


def expand_pdf_reader(name: str) -> tuple[str, ...]:
    """Return the reader list that the single ``pdf_reader`` value means.

    ``pdf_inspector`` brings its rescue tiers (ADR-066). ``auto`` keeps the
    probe order of today's start-up (LiteParse, pypdfium2, pypdf), which the
    "first installed listed reader" rule reproduces. An unknown name reads as
    ``auto``, as ``Settings`` does. Any other known name stands alone.
    """
    if name == "pdf_inspector":
        return PDF_READERS_DEFAULT
    if name in AUTO_READERS:
        return (name,)
    return AUTO_READERS


def expand_ocr_engines(primary: str, fallback: str) -> tuple[str, ...]:
    """Return the engine list that ``ocr_engine_primary`` and ``ocr_engine_fallback`` mean.

    A blank name is left out, so an empty fallback gives a list of one engine.
    A fallback equal to the primary stays in the list, so the index identity
    of such a configuration does not move.
    """
    return tuple(name for name in (primary.strip(), fallback.strip()) if name)


def reader_list(settings: Any) -> tuple[str, ...]:
    """Return the reader order of an ``EffectiveSettings``.

    Compose fills ``pdf_readers`` from ``Settings``. A caller that built the
    object from ``pdf_reader`` alone (a test factory, a ``model_copy`` of
    ``pdf_reader``) leaves it empty, and the single value expands instead.
    """
    return tuple(settings.pdf_readers) or expand_pdf_reader(settings.pdf_reader)


def engine_list(settings: Any) -> tuple[str, ...]:
    """Return the engine order of an ``EffectiveSettings``; see :func:`reader_list`."""
    return tuple(settings.ocr_engines) or expand_ocr_engines(
        settings.ocr_engine_primary, settings.ocr_engine_fallback
    )
