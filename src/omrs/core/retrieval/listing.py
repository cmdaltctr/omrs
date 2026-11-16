"""List collections with document and chunk counts.

Moved out of ``pipeline.py`` so that module stays under the 500-line
ceiling. ``pipeline`` re-exports :func:`list_collections`.
"""

from __future__ import annotations

from ..vectordb import get_default_store
from ..vectordb.base import VectorStore


def list_collections(
    store: VectorStore | None = None,
) -> list[dict]:
    """List all collections with document and chunk counts.

    Args:
        store: Optional injected :class:`VectorStore`.

    Returns:
        A list of dicts, each with:
        - ``name``: collection name
        - ``document_count``: approximate number of unique source files
        - ``chunk_count``: total number of chunks in the collection
    """
    resolved_store = store if store is not None else get_default_store()

    collections: list[dict] = []
    for name in resolved_store.list_collections():
        try:
            chunk_count = resolved_store.count(name)
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in resolved_store.iter_metadatas(name):
                    if meta is None:
                        continue
                    source = meta.get("file_path") or meta.get("file_name") or "unknown"
                    doc_sources.add(source)

            collections.append(
                {
                    "name": name,
                    "document_count": len(doc_sources),
                    "chunk_count": chunk_count,
                }
            )
        except Exception:  # noqa: S112
            # Skip collections that can't be accessed
            continue
    return collections
