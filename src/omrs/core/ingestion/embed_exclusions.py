"""The embedding-text exclusion contract (capability embedding-text-composition).

Split out of ``core/ingestion/source_state.py``, which sits at the 500-line
ceiling, the same way ``ocr_identity`` was. The contract is one concern: which
metadata keys never reach the embedding model, and which of those describe only
one routing unit.

Both members are read through their module at call time, never frozen at
import, so a test override stays observable and a change to the set
invalidates the index identity precisely.
"""

from __future__ import annotations

#: ``_RETAINED_EMBED_METADATA_KEYS`` instead.

EXCLUDED_EMBED_METADATA_KEYS = (
    # Parser telemetry — diagnostics about how a file was parsed, constant
    # across every chunk of a document (``pdf_inspector`` emits the first
    # four; page/layout keys cover the other readers).
    "pdf_reader",
    "pdf_type",
    "pdf_confidence",
    "ocr_required",
    "ocr_used",
    "ocr_backend",
    "pages_needing_ocr",
    "pages_needing_ocr_before_fallback",
    "extraction_fallback_backend",
    # Page-source counts, emitted only by the page routing unit. Constant
    # across a document's chunks, like every parser diagnostic above.
    "ocr_pages_native",
    "ocr_pages_local",
    "ocr_pages_worker",
    "ocr_pages_blank",
    "ocr_pages_unresolved",
    # Maths-page count (modular-ocr-workers-dots-mocr, maths-page-routing).
    "pages_maths_font",
    # Non-Latin page count (non-latin-script-routing); stamped only when the
    # setting is not ``off``.
    "pages_non_latin",
    "page_count",
    "page",
    "page_label",
    "column",
    "section_bbox",
    "bbox_schema_version",
    # Filesystem bookkeeping — machine-specific paths and timestamps that
    # differ between the machine that ingested and any other.
    "file_path",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "last_accessed_date",
)

#: Keys in :data:`EXCLUDED_EMBED_METADATA_KEYS` that the index identity's
#: excluded-key list leaves out. ``pages_non_latin`` exists only while
#: ``ocr_non_latin_routing`` is on, and that setting has its own identity block,
#: so listing the key would change the digest of every default install.
IDENTITY_UNLISTED_KEYS = frozenset({"pages_non_latin"})
