"""Plugin files shipped inside the ``omrs`` package (design D6).

The marimo manifest and the empty notebook template are package data under
``shipped/marimo/``, found through :mod:`importlib.resources`, so a source
checkout and an installed wheel both find them. A registration stores the
manifest path and reads the file again later, so only a real file on disk
counts; a resource inside a zip import is skipped with one warning.
"""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE = "omrs.core.plugins"
_SHIPPED_PLUGINS = ("marimo",)
_EMPTY_NOTEBOOK = ("shipped", "marimo", "empty_notebook.py.template")


def shipped_manifests() -> tuple[Path, ...]:
    """Return the shipped manifest files that exist on disk.

    Returns:
        One path per shipped plugin whose manifest is a regular file. Empty
        when the package is not installed as plain files (for example a zip).
    """
    found: list[Path] = []
    missing: list[str] = []
    for plugin in _SHIPPED_PLUGINS:
        resource = files(_PACKAGE) / "shipped" / plugin / "manifest.json"
        if isinstance(resource, Path) and resource.is_file():
            found.append(resource)
        else:
            missing.append(plugin)
    if missing:
        logger.warning(
            "shipped plugin manifests are not plain files on disk, so they cannot be "
            "registered: %s",
            ", ".join(missing),
        )
    return tuple(found)


def empty_notebook_text() -> str:
    """Return the UTF-8 text of the packaged empty marimo notebook template."""
    return files(_PACKAGE).joinpath(*_EMPTY_NOTEBOOK).read_text(encoding="utf-8")
