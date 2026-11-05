"""Lazy registry of page renderers (change document-reading-routers, design D5).

A page renderer turns one PDF page into a PNG for an image router. It is not a
reading part: it has no descriptor and no entry-point group. Each
``register()`` line below names a renderer and the module it needs; the probe
finds that module without importing it. Importing this module imports no
renderer.
"""

from __future__ import annotations

from ...part_registry import PartRegistry

#: The order the renderers are tried in; the first available one renders.
ORDER: tuple[str, ...] = ("liteparse", "pypdfium2")

#: The registry the function below writes to.
RENDERERS = PartRegistry("page renderer")


def register(name: str, import_path: str, *, probe_module: str) -> None:
    """Register a page renderer. Registering a name again replaces it.

    Args:
        name: Renderer name, as ``ORDER`` lists it.
        import_path: ``"module:attr"`` of the renderer object. Not imported here.
        probe_module: Top-level module the renderer needs. The availability
            probe finds it without importing it.
    """
    RENDERERS.register(name, import_path, probe_module=probe_module)


register(
    "liteparse", "omrs.integrations.pdf.page_images.liteparse:RENDERER", probe_module="liteparse"
)
register(
    "pypdfium2", "omrs.integrations.pdf.page_images.pypdfium2:RENDERER", probe_module="pypdfium2"
)
