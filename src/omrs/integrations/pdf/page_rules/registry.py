"""Lazy registry of page rules (change local-ocr-backends, design D3, D4 and D6).

Each ``register()`` line below has a part descriptor in
``core/reading_parts.py`` (``PAGE_RULES``); ``tests/unit/test_reading_parts_pins.py``
pins the two to each other. The order and the four hook flags are declared
facts. Importing this module imports no rule module.
"""

from __future__ import annotations

from typing import Any

from ...part_registry import PartRegistry

#: The ``source`` of a rule that ships with OMRS. A discovered rule names its
#: distribution instead.
SOURCE_BUILT_IN = "built-in"

#: The shared registry the module functions below delegate to.
RULES = PartRegistry("page rule")


def register(
    name: str,
    import_path: str,
    *,
    order: int,
    drops_pages: bool = False,
    sends_direct: bool = False,
    has_post_check: bool = False,
    has_degrade: bool = False,
    adds_pages: bool = False,
    source: str = SOURCE_BUILT_IN,
) -> None:
    """Register a page rule. Registering a name again replaces it.

    Args:
        name: Rule name.
        import_path: ``"module:attr"`` of the rule object. It is not imported here.
        order: Position among the rules; lower runs first.
        drops_pages: True when the rule can drop a page.
        sends_direct: True when the rule can send a page straight to OCR.
        has_post_check: True when the rule has a ``post_check`` hook.
        has_degrade: True when the rule has a ``degrade`` hook.
        adds_pages: True when the rule can add unflagged pages to the OCR route.
        source: ``built-in``, or the distribution that adds the rule.
    """
    RULES.register(
        name,
        import_path,
        order=order,
        drops_pages=drops_pages,
        sends_direct=sends_direct,
        has_post_check=has_post_check,
        has_degrade=has_degrade,
        adds_pages=adds_pages,
        source=source,
    )


def describe(name: str) -> dict[str, Any]:
    """Return the import path, probe module and declared facts of *name*.

    Raises:
        KeyError: If *name* is not registered.
    """
    return RULES.describe(name)


def available() -> list[str]:
    """Return the registered rule names, sorted by name."""
    return RULES.names()


def ordered() -> list[tuple[str, dict[str, Any]]]:
    """Return ``(name, facts)`` of every registered rule, in ascending order."""
    entries = [(name, RULES.describe(name)) for name in RULES.names()]
    return sorted(entries, key=lambda entry: (entry[1]["order"], entry[0]))


register("blank", "omrs.integrations.pdf.page_rules.blank:RULE", order=10, drops_pages=True)
register("maths", "omrs.integrations.pdf.page_rules.maths:RULE", order=20, sends_direct=True)
register(
    "non_latin",
    "omrs.integrations.pdf.page_rules.non_latin:RULE",
    order=30,
    sends_direct=True,
    has_post_check=True,
    has_degrade=True,
)
