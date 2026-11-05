"""Problem kinds and the type rule text of one field (moved out of ``settings_file``).

``settings_file`` reads flat and nested settings, and ``settings_maps`` reads the
named maps. Both name a broken value with the same kinds and the same rule text,
so the two live here. ``settings_file`` re-exports every name.

This module is a leaf: it imports only ``config.rules``. A rule text names a kind
and a range, never a value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_args, get_origin

from .rules import LIST_TYPE_RULE

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

#: Problem kinds.
KIND_BROKEN = "broken"
KIND_INVALID = "invalid"
KIND_UNKNOWN = "unknown"
KIND_RETIRED = "retired"


def field_bounds(info: FieldInfo) -> dict[str, Any]:
    """Return the ``ge``, ``gt``, ``le`` and ``lt`` bounds that *info* declares."""
    found: dict[str, Any] = {}
    for item in info.metadata:
        for name in ("ge", "gt", "le", "lt"):
            if getattr(item, name, None) is not None:
                found[name] = getattr(item, name)
    return found


#: The text of a one-sided bound, in the order the rule text tries them.
_ONE_SIDED = (
    ("gt", "greater than"),
    ("ge", "of at least"),
    ("lt", "less than"),
    ("le", "of at most"),
)


def rule_text(info: FieldInfo) -> str:
    """Describe the type rule of a field. It names a kind and a range, never a value."""
    if get_origin(info.annotation) is tuple:
        return LIST_TYPE_RULE
    names = {info.annotation, *get_args(info.annotation)}
    bounds = field_bounds(info)
    low, high = bounds.get("ge", bounds.get("gt")), bounds.get("le", bounds.get("lt"))
    if bool in names:
        return "The value must be true or false."
    kind = "a whole number" if int in names else "a number" if float in names else None
    if kind is None:
        return "The value must be text." if str in names else "The value is not valid."
    span = f" from {low} to {high}" if low is not None and high is not None else ""
    if not span:
        span = next((f" {text} {bounds[name]}" for name, text in _ONE_SIDED if name in bounds), "")
    return f"The value must be {kind}{span}."
