"""Lazy registry of local OCR backends (change local-ocr-backends, design D3, D7 and D9).

The ``register()`` line below and the descriptor in ``core/reading_parts.py``
(``LOCAL_OCR_BACKENDS``) describe one backend; ``tests/unit/test_reading_parts_pins.py``
pins the two to each other. Importing this module imports no backend module.

A backend that panics is switched off here for the rest of the process (design
D17), per backend: the other listed backends keep reading.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ...part_registry import PartRegistry

#: The list the local tier reads with when the settings name none.
DEFAULT_BACKENDS: tuple[str, ...] = ("pp-ocrv6-small",)

#: The registry the functions below write to.
BACKENDS = PartRegistry("local OCR backend")


def register(
    name: str,
    import_path: str,
    *,
    producer: str,
    min_confidence: float | None = None,
    calibrated_by: str | None = None,
    keeps_scripts: Iterable[str] | None = None,
    probe_module: str | None = None,
) -> None:
    """Register a local OCR backend. Registering a name again replaces it.

    Args:
        name: Backend name, as the ``ocr_local_backends`` setting lists it.
        import_path: ``"module:attr"`` of the backend object. Not imported here.
        producer: The ``ocr_backend`` value of a page the backend keeps.
        min_confidence: The calibrated escalation cut, or ``None`` (not listable).
        calibrated_by: The experiment folder that measured the cut.
        keeps_scripts: Lower-case Unicode script names the backend may keep, or
            ``None`` for no script filter.
        probe_module: Module the backend needs. Defaults to the import path's.

    Raises:
        ValueError: A cut without the experiment that measured it.
    """
    if min_confidence is not None and not calibrated_by:
        raise ValueError(
            f"local OCR backend {name!r} has a cut ({min_confidence}) but no calibrated_by"
        )
    BACKENDS.register(
        name,
        import_path,
        probe_module=probe_module,
        producer=producer,
        min_confidence=min_confidence,
        calibrated_by=calibrated_by,
        keeps_scripts=None if keeps_scripts is None else frozenset(keeps_scripts),
    )


def describe(name: str) -> dict[str, Any]:
    """Return the import path, probe module and facts of *name*.

    Raises:
        KeyError: If *name* is not registered.
    """
    return BACKENDS.describe(name)


def available() -> list[str]:
    """Return the registered backend names, sorted."""
    return BACKENDS.names()


def installed(name: str) -> bool:
    """Return whether the probe module of *name* is installed; imports nothing."""
    return BACKENDS.installed(name)


def listed(settings: Any) -> tuple[str, ...]:
    """Return the injected backend list, or :data:`DEFAULT_BACKENDS` without one."""
    return tuple(getattr(settings, "ocr_local_backends", DEFAULT_BACKENDS))


def effective_cut(name: str, settings: Any) -> float | None:
    """Return the cut of *name*: the operator override when set, else its own cut."""
    override = getattr(settings, "ocr_local_min_confidence", None)
    return describe(name)["min_confidence"] if override is None else override


def switch_off(name: str, reason: str) -> None:
    """Switch *name* off for the rest of the process."""
    BACKENDS.switch_off(name, reason)


def off_reason(name: str) -> str | None:
    """Return why *name* is off for this process, or ``None`` when it is on."""
    return BACKENDS.off_reason(name)


register(
    "pp-ocrv6-small",
    "omrs.integrations.pdf.local_ocr.pp_ocrv6_small:BACKEND",
    producer="pdf_inspector_ocr",
    min_confidence=0.9,
    calibrated_by="39-local-tier-escalation-2026-09-30",
    keeps_scripts=None,
    probe_module="pdf_inspector",
)
register(
    "indra",
    "omrs.integrations.pdf.local_ocr.indra:BACKEND",
    producer="indra_ocr",
    min_confidence=0.90,
    calibrated_by="46-local-ocr-backends-2026-11-04",
    keeps_scripts={"arabic", "devanagari"},
    probe_module="indra_ocr",
)
