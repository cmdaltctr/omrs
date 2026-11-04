"""Lazy registry for concrete PDF reader adapters.

``auto`` is deliberately absent: it is a capability-resolution policy owned
by ``compose.resolve_pdf_reader`` and :mod:`integrations.pdf.factory`, not a
reader implementation.  The three concrete values accepted by
``PDF_READER`` resolve through this registry and share the ``load_data``
contract expected by LlamaIndex's ``SimpleDirectoryReader``.

Each entry carries its declared metadata (spec pdf-reader: "Readers declare
their emitted text format"): ``text_format`` (what the reader emits —
downstream consumers route on it instead of inferring format from the
source extension), ``page_provenance`` (whether the reader can observe
page boundaries) and ``output_revision`` (an integer that rises when a
reader change alters the documents it emits for the same file; the index
identity of PDF sources hashes it, change pdf-inspector-page-provenance).
Inspect them with :func:`describe`.

The entries live on the shared page-reading registry helper
(:class:`integrations.part_registry.PartRegistry`, change local-ocr-backends,
design D4). Each ``register()`` line below has a part descriptor in
``core/reading_parts.py``; ``tests/unit/test_reading_parts_pins.py`` pins the
two to each other (design D3).

Importing this module does NOT import any adapter or optional dependency.
"""

from __future__ import annotations

from typing import Any, Literal

from ..part_registry import PartRegistry

#: The text format a reader declares for its emitted documents
#: (spec pdf-reader: "Readers declare their emitted text format").
#: Downstream consumers route on this declaration instead of inferring
#: format from the source file's extension.
TextFormat = Literal["plain", "markdown"]

#: The shared registry the module functions below delegate to.
READERS = PartRegistry("PDF reader")
#: The live cache of loaded reader classes. Tests stub a reader with
#: ``monkeypatch.setitem(registry._cache, name, Stub)``.
_cache: dict[str, Any] = READERS.cache


def register(
    name: str,
    import_path: str,
    probe_module: str | None = None,
    *,
    text_format: TextFormat,
    page_provenance: bool,
    output_revision: int = 1,
) -> None:
    """Register a concrete PDF reader class and its dependency probe.

    Args:
        name: Concrete ``PDF_READER`` value.
        import_path: ``"module:ClassName"`` import string.
        probe_module: Importable dependency required by the reader. Defaults
            to the adapter module from ``import_path``.
        text_format: REQUIRED declaration of the emitted text format
            (``"plain"`` or ``"markdown"``). Registration fails without it —
            a new reader must never default silently.
        page_provenance: Whether the reader can observe page boundaries
            (emits ``page_label``); machine-discoverable capability.
        output_revision: Revision of the documents the reader emits. Raise
            it when a reader change alters the output for the same file, so
            PDF sources reprocess once on their next ingest.

    Raises:
        ValueError: If ``text_format`` is not ``"plain"`` or
            ``"markdown"``.
    """
    if text_format not in ("plain", "markdown"):
        raise ValueError(
            f"PDF reader {name!r} declared text_format={text_format!r}; "
            "expected 'plain' or 'markdown'."
        )
    READERS.register(
        name,
        import_path,
        probe_module=probe_module,
        text_format=text_format,
        page_provenance=page_provenance,
        output_revision=output_revision,
    )


def describe(name: str) -> dict[str, Any]:
    """Return the declared reader metadata for *name*.

    Mirrors the document-backend registry pattern
    (``core/ingestion/backends/registry.py``): the descriptor carries the
    declared ``text_format``, ``page_provenance`` capability and
    ``output_revision`` alongside the import string and dependency probe.

    Raises:
        KeyError: If *name* is not registered (lists available names).
    """
    return READERS.describe(name)


def get(name: str) -> type[Any]:
    """Resolve and cache the reader class for *name*.

    Args:
        name: Registered concrete reader name.

    Returns:
        Reader adapter class with a ``load_data`` method.

    Raises:
        KeyError: If *name* is not registered (lists available names).
        ImportError: If the adapter module cannot be imported.
    """
    return READERS.get(name)


def probe(name: str) -> None:
    """Verify that a registered reader dependency is importable.

    Args:
        name: Concrete ``PDF_READER`` value.

    Raises:
        KeyError: If *name* is not registered.
        ImportError: If the reader dependency is unavailable.
    """
    READERS.probe(name)


def available() -> list[str]:
    """Return the sorted registered concrete reader names."""
    return READERS.names()


register(
    "pypdf",
    "omrs.integrations.pdf.pypdf:PyPDFReader",
    "pypdf",
    text_format="plain",
    page_provenance=True,
)
register(
    "pypdfium2",
    "omrs.integrations.pdf.pypdfium:PyPDFium2Reader",
    "pypdfium2",
    text_format="plain",
    page_provenance=True,
)
register(
    "liteparse",
    "omrs.integrations.pdf.liteparse:LiteParseReader",
    "liteparse",
    text_format="plain",
    page_provenance=True,
)
register(
    "pdf_inspector",
    "omrs.integrations.pdf.pdf_inspector:PdfInspectorReader",
    "pdf_inspector",
    text_format="markdown",
    # Revision 2: one document per page with ``page`` and ``page_label``
    # (change pdf-inspector-page-provenance); revision 1 emitted one
    # whole-document Markdown document.
    page_provenance=True,
    output_revision=2,
)
