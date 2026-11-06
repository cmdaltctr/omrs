"""The ordered local OCR backend list (change local-ocr-backends, design D8).

:func:`read_local_pages` runs the listed backends in order:

1. The first backend that can run reads every page in one call.
2. The shared escalation rule runs on its results with the backend's effective cut
   (its ``ocr_local_cuts`` entry, else its default cut). Confidence alone decides:
   no backend refuses a page because of its script.
3. A page with no reason is kept and names the backend's ``producer``.
4. Every other page passes to the next backend in one call. The last backend that
   read a page gives its reasons.
5. An escalated page carries the text of the first backend, in list order, that
   returned non-empty text for it, so an unresolved page keeps that text.
6. A backend that raises is skipped for the call, with one warning per process
   when another backend reads. A non-``Exception`` panic also switches it off for
   the process. When no listed backend can run, the first failure is raised, so
   the caller's missing-runtime rule applies as before.

With the default list (one backend) steps 4 and 5 change nothing, so the outcome
is the one before the change.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import registry
from .base import BackendPage, LocalOcrPage

logger = logging.getLogger(__name__)

#: Backends this process already warned about as skipped.
_WARNED: set[str] = set()


def reset_skip_warnings() -> None:
    """Forget which skipped backends were warned about (test seam)."""
    _WARNED.clear()


def escalation_reasons(
    result: BackendPage | None, cut: float, facts: dict[str, Any], post_checks: Sequence
) -> list[str]:
    """Return the reasons one backend's read of one page does not keep it.

    Args:
        result: The backend's read of the page, or ``None`` when it returned none.
        cut: The backend's effective cut.
        facts: The backend's registered facts (``producer``, ``min_confidence``).
        post_checks: Page-rule post-checks, each ``check(text, facts)``.

    Returns:
        The reasons in check order; empty when the backend keeps the page.
    """
    text = result.text if result is not None else ""
    confidence = result.confidence if result is not None else None
    reasons: list[str] = []
    if result is None:
        reasons.append("missing_page")
    if not text.strip():
        reasons.append("empty_text")
    # ``None`` escalates with the below-threshold pages: an unreported confidence
    # cannot vouch for the text, and the calibration treated it as zero.
    if confidence is None or confidence < cut:
        reasons.append("low_confidence")
    if result is not None and result.hosted_recommended:
        reasons.append("hosted_recommended")
    reasons += [r for check in post_checks if (r := check(text, facts)) is not None]
    return reasons


def _read_one(name: str, file: Path, pages: list[int], settings: Any) -> list[BackendPage]:
    """Call one backend; switch it off for the process on a panic, then re-raise."""
    try:
        return registry.BACKENDS.get(name).read_pages(file, pages, settings=settings)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        if not isinstance(exc, Exception):
            registry.switch_off(name, f"{type(exc).__name__}: {exc}")
        raise


def _warn_skipped(skipped: list[tuple[str, BaseException]]) -> None:
    for name, exc in skipped:
        if name in _WARNED:
            continue
        _WARNED.add(name)
        logger.warning(
            "Local OCR backend %r skipped (%s: %s); the other listed backends read its pages.",
            name,
            type(exc).__name__,
            exc,
        )


def read_local_pages(
    file: Path, pages: list[int], *, settings: Any, post_checks: Sequence
) -> list[LocalOcrPage]:
    """Read *pages* with the listed local OCR backends, in list order.

    Args:
        file: Path to the PDF file.
        pages: 1-based page numbers. Uniqueness is the caller's guarantee.
        settings: Injected settings (``ocr_local_backends``,
            ``ocr_local_cuts`` and each backend's own fields).
        post_checks: Page-rule post-checks, each ``check(text, facts)``.

    Returns:
        One :class:`LocalOcrPage` per page, in page order.

    Raises:
        BaseException: The first failure, when no listed backend could read.
        RuntimeError: Every listed backend is switched off for the process.
    """
    if not pages:
        return []
    remaining = sorted(pages)
    kept: dict[int, LocalOcrPage] = {}
    last: dict[int, tuple[BackendPage | None, tuple[str, ...]]] = {}
    first_text: dict[int, tuple[BackendPage, str]] = {}
    skipped: list[tuple[str, BaseException]] = []
    ran = False
    for name in registry.listed(settings):
        if not remaining:
            break
        if registry.off_reason(name) is not None:
            continue
        try:
            results = _read_one(name, file, list(remaining), settings)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - a backend that cannot run is skipped
            skipped.append((name, exc))
            continue
        ran = True
        facts = registry.describe(name)
        cut = registry.effective_cut(name, settings)
        by_number = {result.page: result for result in results}
        passing: list[int] = []
        for number in remaining:
            result = by_number.get(number)
            if result is not None and result.text.strip() and number not in first_text:
                first_text[number] = (result, facts["producer"])
            reasons = tuple(escalation_reasons(result, cut, facts, post_checks))
            if reasons:
                last[number] = (result, reasons)
                passing.append(number)
            else:
                kept[number] = _page(number, result, (), facts["producer"])
        remaining = passing
    if not ran:
        if skipped:
            raise skipped[0][1]
        off = [registry.off_reason(name) for name in registry.listed(settings)]
        raise RuntimeError(f"every listed local OCR backend is off: {off[0] if off else None}")
    _warn_skipped(skipped)
    return [
        kept.get(number) or _escalated(number, last[number], first_text) for number in sorted(pages)
    ]


def _page(
    number: int, result: BackendPage | None, reasons: tuple[str, ...], producer: str | None
) -> LocalOcrPage:
    return LocalOcrPage(
        page=number,
        text=result.text if result is not None else "",
        confidence=result.confidence if result is not None else None,
        model=result.model if result is not None else None,
        escalates=bool(reasons),
        reasons=reasons,
        producer=producer,
    )


def _escalated(
    number: int,
    last: tuple[BackendPage | None, tuple[str, ...]],
    first_text: dict[int, tuple[BackendPage, str]],
) -> LocalOcrPage:
    """Return an escalated page: the last backend's reasons, the first text kept."""
    result, reasons = last
    if number in first_text:
        text_result, producer = first_text[number]
        return _page(number, text_result, reasons, producer)
    return _page(number, result, reasons, None)
