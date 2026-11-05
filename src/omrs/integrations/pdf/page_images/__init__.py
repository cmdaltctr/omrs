"""Page images for image routers (change document-reading-routers, design D5).

:func:`render_page` renders one page as a PNG at 150 DPI with the long side at
most 1,568 px, the Experiment 43 values, so the frozen router threshold stays
valid. It uses the first available renderer of ``registry.ORDER``.
:func:`available` is a cheap probe: it imports no renderer.
"""

from __future__ import annotations

from pathlib import Path

from .registry import ORDER, RENDERERS

#: Render resolution in dots per inch.
DPI = 150

#: The longest image side, in pixels.
MAX_LONG_SIDE = 1568


class NoRendererError(Exception):
    """No page renderer is installed."""


def _first_available() -> str | None:
    """Return the first installed renderer of ``ORDER``, or ``None``."""
    return next((name for name in ORDER if RENDERERS.installed(name)), None)


def available() -> bool:
    """Report whether a page renderer is installed, without importing one."""
    return _first_available() is not None


def render_page(file: Path, page: int) -> bytes:
    """Render one page as a PNG at 150 DPI, long side at most 1,568 px.

    A page whose long side is over the cap at 150 DPI renders again at the
    DPI that gives the cap. A renderer that rounds that size up renders a
    third time, one pixel smaller.

    Args:
        file: Path to the PDF file.
        page: Page number, from 1, as in the page scan.

    Returns:
        The PNG bytes.

    Raises:
        NoRendererError: If no page renderer is installed.
        ValueError: If the image is still over the cap after the third render.
    """
    name = _first_available()
    if name is None:
        raise NoRendererError(f"No page renderer is installed. Tried: {', '.join(ORDER)}")
    renderer = RENDERERS.get(name)
    png, size = renderer.render(file, page, DPI)
    if max(size) <= MAX_LONG_SIDE:
        return png
    dpi = DPI * MAX_LONG_SIDE / max(size)
    png, size = renderer.render(file, page, dpi)
    if max(size) <= MAX_LONG_SIDE:
        return png
    png, size = renderer.render(file, page, dpi * (MAX_LONG_SIDE - 1) / max(size))
    if max(size) > MAX_LONG_SIDE:
        raise ValueError(f"Page renderer {name!r} gave a {max(size)} px side; the cap is 1568")
    return png
