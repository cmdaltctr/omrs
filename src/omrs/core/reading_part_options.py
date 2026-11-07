"""Lookups for the ``reading_part_options`` map (change local-ocr-backends, design D12).

Moved out of ``core/reading_parts.py`` (change page-routing-panel), which sits
at the 500-line ceiling. ``reading_parts.py`` may import only the standard
library, so it cannot re-export these names; their two callers
(``compose_settings.py`` and ``core/ingestion/reader_identity.py``) import them
from here. The tables are read through the module at call time, so a test that
patches a table on ``reading_parts`` still takes effect.
"""

from __future__ import annotations

from . import reading_parts
from .reading_parts import PartDescriptor, SettingField

#: The implicit option of every page rule (design D12). A discovered rule runs
#: only when it is ``true``; a built-in rule ignores it.
RULE_ENABLED_OPTION = SettingField(name="enabled", env="", default=False)


def parts_named(name: str) -> tuple[PartDescriptor, ...]:
    """Return every built-in and discovered descriptor called *name*, of any kind."""
    table = (
        *reading_parts.PDF_READERS,
        *reading_parts.LOCAL_OCR_BACKENDS,
        *reading_parts.PAGE_RULES,
        *reading_parts.discovered(),
    )
    return tuple(d for d in table if d.name == name)
