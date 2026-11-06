"""Health rows of reading parts for ``GET /v1/integrations`` (change local-ocr-backends, D14).

The rows come from the part descriptors (``core/reading_parts.py``) and the
page-reading registries, so a new part shows here with no edit:

- local OCR backends: one row per backend in ``ocr_local_backends``, in list
  order, with the install probe, the model files of the descriptor, the
  per-process switch-off reason and the effective cut;
- page rules: one row per registered rule, in rule order, with on or off,
  the version and the source;
- discovered parts: one row per entry point that discovery found.

Every check only reads. No check imports a part, downloads a file or starts
a process. A section whose check raises is an empty list; the detail goes
to the log. This module imports no web framework.

A reason or problem text is cleaned before it leaves the server: the home
folder becomes ``~`` and the text is capped at :data:`MAX_REASON_CHARS`. The
log keeps the full text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...core import reading_parts
from ...integrations import part_registry
from ...integrations.pdf.local_ocr import registry as local_ocr_registry
from ...integrations.pdf.page_rules import registry as page_rule_registry
from .runtime_components import model_folder

logger = logging.getLogger(__name__)


#: What discovery found (``part_registry.DiscoveredPart`` items).
Found = tuple[Any, ...]

#: The longest reason or problem text a row carries, ellipsis included.
MAX_REASON_CHARS = 300


def _clean(text: str | None) -> str | None:
    """Return *text* with the home folder as ``~`` and at most :data:`MAX_REASON_CHARS`.

    A panic or a ``dlopen`` error can hold a full path under the home folder.
    """
    if text is None:
        return None
    home = str(Path.home()).rstrip("/\\")
    if home:
        text = re.sub(re.escape(home) + r"(?![\w.-])", "~", text)
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 1] + "…"
    return text


def _descriptors(table: tuple[Any, ...], kind: str, found: Found) -> dict[str, Any]:
    """Return the built-in and the accepted discovered descriptors of one kind, by name."""
    discovered = {
        part.name: part.descriptor
        for part in found
        if part.kind == kind and part.descriptor is not None and part.name
    }
    return {**discovered, **{part.name: part for part in table}}


def _model_present(settings: Any, descriptor: Any) -> bool | None:
    """Return whether every model file is on disk, or ``None`` when none is named."""
    files = descriptor.health.model_files if descriptor is not None else ()
    folder = model_folder(settings, descriptor) if files else None
    if folder is None:
        return None
    return all((folder / name).is_file() for name in files)


def _installed(name: str) -> bool:
    try:
        return local_ocr_registry.BACKENDS.installed(name)
    except KeyError:  # Listed but not registered: nothing can load it.
        return False


def _cut(settings: Any, descriptor: Any) -> float | None:
    """Return the cut the backend applies: its ``ocr_local_cuts`` entry, else its default."""
    return None if descriptor is None else reading_parts.effective_cut(settings, descriptor.name)


def local_backend_rows(settings: Any, found: Found = ()) -> list[dict[str, Any]]:
    """Return one row per listed local OCR backend, in list order."""
    kind = reading_parts.KIND_LOCAL_OCR_BACKEND
    known = _descriptors(reading_parts.LOCAL_OCR_BACKENDS, kind, found)
    rows = []
    for name in local_ocr_registry.listed(settings):
        descriptor = known.get(name)
        rows.append(
            {
                "name": name,
                "label": descriptor.label if descriptor is not None else name,
                "installed": _installed(name),
                "model_present": _model_present(settings, descriptor),
                "off_reason": _clean(local_ocr_registry.off_reason(name)),
                "effective_cut": _cut(settings, descriptor),
                "source": descriptor.source if descriptor is not None else "built-in",
            }
        )
    return rows


def _rule_enabled(settings: Any, name: str, descriptor: Any, source: str) -> bool:
    """Return whether rule *name* runs under *settings* (design D12).

    A discovered rule runs only when its ``enabled`` option is true. A built-in
    rule follows its first setting: a flag as it is, a choice unless ``off``,
    a free-text name (the router) when it is not empty or ``none``.
    A built-in rule without a setting always runs.
    """
    if source != reading_parts.SOURCE_BUILT_IN:
        options = (getattr(settings, "reading_part_options", None) or {}).get(name) or {}
        return options.get("enabled") is True
    fields = descriptor.settings if descriptor is not None else ()
    if not fields:
        return True
    value = getattr(settings, fields[0].name, fields[0].default)
    if fields[0].accepted is not None:
        return value != "off"
    if isinstance(fields[0].default, bool):
        return value is True
    return bool(value) and value != "none"


def page_rule_rows(settings: Any, found: Found = ()) -> list[dict[str, Any]]:
    """Return one row per registered page rule, in rule order."""
    known = _descriptors(reading_parts.PAGE_RULES, reading_parts.KIND_PAGE_RULE, found)
    rows = []
    for name, facts in page_rule_registry.ordered():
        descriptor = known.get(name)
        source = facts.get("source", reading_parts.SOURCE_BUILT_IN)
        rows.append(
            {
                "name": name,
                "label": descriptor.label if descriptor is not None else name,
                "enabled": _rule_enabled(settings, name, descriptor, source),
                "version": descriptor.version if descriptor is not None else 1,
                "source": source,
            }
        )
    return rows


def discovered_rows(found: Found) -> list[dict[str, Any]]:
    """Return one row per entry point that discovery found (accepted or not)."""
    return [
        {
            "name": part.name,
            "kind": part.kind,
            "distribution": part.distribution,
            "version": part.version,
            "problem": _clean(part.problem),
        }
        for part in found
    ]


def _guarded(section: str, build: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    try:
        return build()
    except Exception:
        # Detail stays in the (redacted) log. The client gets an empty section.
        logger.warning("Reading part health %r could not be read.", section, exc_info=True)
        return []


def reading_parts_health(settings: Any | None) -> dict[str, list[dict[str, Any]]]:
    """Return the ``reading_parts`` block of ``GET /v1/integrations``.

    Args:
        settings: The Engine's frozen ``EffectiveSettings``, or ``None`` when
            they cannot be read. ``None`` gives three empty sections.

    Returns:
        ``local_ocr_backends``, ``page_rules`` and ``discovered_parts`` lists.
    """
    if settings is None:
        return {"local_ocr_backends": [], "page_rules": [], "discovered_parts": []}
    try:
        found: Found = tuple(part_registry.discovered_parts())
    except Exception:
        logger.warning("The discovered reading parts could not be read.", exc_info=True)
        found = ()
    return {
        "local_ocr_backends": _guarded(
            "local_ocr_backends", lambda: local_backend_rows(settings, found)
        ),
        "page_rules": _guarded("page_rules", lambda: page_rule_rows(settings, found)),
        "discovered_parts": _guarded("discovered_parts", lambda: discovered_rows(found)),
    }
