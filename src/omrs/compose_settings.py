"""Server-default :class:`EffectiveSettings` construction (change page-level-ocr-routing).

Split out of ``compose.py``, which sits at the 500-line ceiling, the same way
``compose_answer`` and ``compose_engine`` were. ``compose`` re-exports
:func:`settings_to_effective`, so every existing import site is unchanged.

It also runs entry-point discovery of reading parts before settings resolve,
and checks ``reading_part_options`` against the part descriptors (change
local-ocr-backends, design D11 and D12).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from .capabilities import (
    _resolve_sparse_backend_for,
    resolve_document_backend,
    resolve_pdf_readers,
)
from .config import Settings, get_settings
from .core.settings import (
    PROVIDER_ADDRESS_FIELDS,
    PROVIDER_INT_FIELDS,
    PROVIDER_SECRET_FIELDS,
    OcrNonLatinMode,
)

logger = logging.getLogger(__name__)

#: ``(kind, name)`` of the broken parts a setting named, already warned about
#: for :data:`_warned_for` (one discovery result).
_warned: set[tuple[str, str]] = set()
_warned_for: tuple[Any, ...] | None = None


def discover_reading_parts() -> tuple[Any, ...]:
    """Run reading-part discovery once per process and let settings accept the parts.

    :func:`compose.get_settings` calls this before it resolves ``Settings``. The
    accepted descriptors join the lookups of ``core.reading_parts``, which
    ``config/`` reads when it checks a part name. ``config`` itself never
    runs discovery, so importing it reads no entry point (design D11).

    Returns:
        Every discovered entry point, accepted or not.
    """
    from .core import reading_parts as parts
    from .integrations.part_registry import discover_parts

    found = discover_parts(
        builtin_names={
            parts.KIND_PDF_READER: parts.names(parts.PDF_READERS),
            parts.KIND_LOCAL_OCR_BACKEND: parts.names(parts.LOCAL_OCR_BACKENDS),
            parts.KIND_PAGE_RULE: parts.names(parts.PAGE_RULES),
        },
        descriptor_types={
            parts.KIND_PDF_READER: parts.PdfReaderDescriptor,
            parts.KIND_LOCAL_OCR_BACKEND: parts.LocalOcrBackendDescriptor,
            parts.KIND_PAGE_RULE: parts.PageRuleDescriptor,
        },
    )
    parts.install_discovered(
        (cast(Any, p.descriptor) for p in found if p.descriptor is not None),
        ((p.kind, p.name, p.problem) for p in found if p.broken),
    )
    global _warned_for
    if found is not _warned_for:
        _warned_for = found
        _warned.clear()
    return found


def warn_broken_parts_named(settings: Any) -> None:
    """Log one warning per broken discovered part that a setting names (finding 4).

    The setting is accepted and the part is off: the registries hold it off
    from discovery on, so the local tier, the page rules and the reader chain
    skip it.
    """
    from .core import reading_parts as parts

    named = {
        parts.KIND_PDF_READER: tuple(getattr(settings, "pdf_readers", ())),
        parts.KIND_LOCAL_OCR_BACKEND: tuple(getattr(settings, "ocr_local_backends", ())),
        parts.KIND_PAGE_RULE: tuple(getattr(settings, "reading_part_options", None) or {}),
    }
    for kind, names in named.items():
        broken = parts.broken(kind)
        for name in names:
            if name in broken and (kind, name) not in _warned:
                _warned.add((kind, name))
                logger.warning(
                    "The settings name the %s %r, which is broken and stays off: %s.",
                    kind.replace("_", " "),
                    name,
                    broken[name],
                )


def _value_problem(option: Any, value: Any) -> str | None:
    """Return the rule that *value* breaks for one ``SettingField``, or ``None``."""
    if option.accepted is not None and value not in option.accepted:
        return f"the value must be one of: {', '.join(option.accepted)}"
    if option.default is None:
        return None
    kind = type(option.default)
    if kind is float:
        fits = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        fits = type(value) is kind
    return None if fits else f"the value must be of type {kind.__name__}"


def part_options_problem(options: Mapping[str, Mapping[str, Any]]) -> str | None:
    """Return why ``reading_part_options`` is not valid, or ``None`` (design D12).

    Each key must name a built-in or discovered part, and each option must be
    one its descriptor declares, with a value of the declared type and accepted
    set. Every page rule also takes ``enabled`` (a built-in rule ignores it).
    The rule names the part and the key, never the value.
    """
    from .core import reading_parts as parts

    for name, values in options.items():
        found = parts.parts_named(name)
        if not found and name in parts.broken():
            continue  # A broken part has no descriptor to check; it is off (finding 4).
        if not found:
            return f"{name!r} is not a reading part."
        known = {option.name: option for part in found for option in part.options}
        if any(part.kind == parts.KIND_PAGE_RULE for part in found):
            known.setdefault(parts.RULE_ENABLED_OPTION.name, parts.RULE_ENABLED_OPTION)
        for key, value in values.items():
            option = known.get(key)
            if option is None:
                choices = ", ".join(sorted(known)) or "none"
                return f"Part {name!r} has no option {key!r}. Its options: {choices}."
            rule = _value_problem(option, value)
            if rule is not None:
                return f"Option {key!r} of part {name!r}: {rule}."
    return None


def settings_to_effective(settings: Settings | None = None) -> Any:
    """Produce the server-default :class:`EffectiveSettings` from resolved ``Settings``.

    This is the adapter that bridges the config layer (flat ``Settings``)
    and the core layer (frozen ``EffectiveSettings``). The
    :class:`ProfileResolver` overlays only profile-owned levers (task 4.4).

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A frozen :class:`EffectiveSettings` with cross-cutting fields.
    """
    from .core.settings import (
        AnswerBlock,
        ChunkingBlock,
        EffectiveSettings,
        EmbeddingBlock,
        IngestionBlock,
        MetadataBlock,
        RetrievalBlock,
    )

    if settings is None:
        discover_reading_parts()  # this path reads Settings without compose.get_settings
        settings = get_settings()

    if settings.chunking.chunk_overlap >= settings.chunking.markdown_chunk_size:
        raise ValueError("CHUNKING__CHUNK_OVERLAP must be less than CHUNKING__MARKDOWN_CHUNK_SIZE")
    problem = part_options_problem(settings.reading_part_options)
    if problem is not None:
        raise ValueError(f"READING_PART_OPTIONS is not valid. {problem}")
    warn_broken_parts_named(settings)

    # Bake the RESOLVED reader and the cleaned list in: the probe and the
    # `auto` / unknown-name warnings run once here (ordered-reader-and-ocr-lists D2).
    pdf_reader, pdf_readers = resolve_pdf_readers(settings)

    # Nested Settings blocks map 1:1 onto EffectiveSettings blocks — a
    # straight copy plus cross-cutting fields (pre-nested-schema: ~30 names).
    return EffectiveSettings(
        chunking=ChunkingBlock(**settings.chunking.model_dump()),
        ingestion=IngestionBlock(**settings.ingestion.model_dump()),
        embedding=EmbeddingBlock(**settings.embedding.model_dump()),
        retrieval=RetrievalBlock(
            **{
                **settings.retrieval.model_dump(),
                # Bake the RESOLVED backend in: the `auto` probe runs
                # once here, so core/ performs a plain read (task 7.10).
                "hybrid_sparse_backend": _resolve_sparse_backend_for(settings),
            }
        ),
        metadata=MetadataBlock(**settings.metadata.model_dump()),
        answer=AnswerBlock(**settings.answer.model_dump()),
        profile_name=settings.rag_profile,
        chroma_persist_dir=settings.chroma_persist_dir,
        collection_name=settings.collection_name,
        chroma_scan_page_size=settings.chroma_scan_page_size,
        vector_store=settings.vector_store,
        lancedb_uri=settings.lancedb_uri,
        embed_provider=settings.embed_provider,
        metadata_llm_provider=settings.metadata_llm_provider,
        local_backend=settings.local_backend,
        cloud_backend=settings.cloud_backend,
        llamacpp_embed_url=settings.llamacpp_embed_url,
        llamacpp_embed_model=settings.llamacpp_embed_model,
        llamacpp_chat_model=settings.llamacpp_chat_model,
        openrouter_embed_model=settings.openrouter_embed_model,
        openrouter_llm_model=settings.openrouter_llm_model,
        **{
            name: getattr(settings, name)
            for name in PROVIDER_ADDRESS_FIELDS + PROVIDER_SECRET_FIELDS + PROVIDER_INT_FIELDS
        },
        embed_model=settings.embed_model,
        pdf_reader=pdf_reader,
        pdf_readers=pdf_readers,
        liteparse_num_workers=settings.liteparse_num_workers,
        liteparse_ocr_enabled=settings.liteparse_ocr_enabled,
        ocr_fallback_enabled=settings.ocr_fallback_enabled,
        ocr_routing_unit=settings.ocr_routing_unit,
        ocr_local_min_confidence=settings.ocr_local_min_confidence,
        ocr_local_backends=settings.ocr_local_backends,
        ocr_local_offline=settings.ocr_local_offline,
        ocr_local_model_directory=settings.ocr_local_model_directory,
        reading_part_options=settings.reading_part_options,
        ocr_worker_request_timeout=settings.ocr_worker_request_timeout,
        ocr_workers_dir=settings.ocr_workers_dir,
        ocr_runtime_url=settings.ocr_runtime_url,
        ocr_engine_primary=settings.ocr_engine_primary,
        ocr_engine_fallback=settings.ocr_engine_fallback,
        ocr_engines=settings.ocr_engines,
        ocr_maths_routing_enabled=settings.ocr_maths_routing_enabled,
        # Settings checked the value against OCR_NON_LATIN_MODES at start-up.
        ocr_non_latin_routing=cast(OcrNonLatinMode, settings.ocr_non_latin_routing),
        ocr_worker_seconds_per_page=settings.ocr_worker_seconds_per_page,
        magika_binary=settings.magika_binary,
        doc_similarity_threshold=settings.doc_similarity_threshold,
        codebase_map_cache_dir=settings.codebase_map_cache_dir,
        codebase_map_max_files=settings.codebase_map_max_files,
        codebase_map_max_depth=settings.codebase_map_max_depth,
        community_algorithm=settings.community_algorithm.strip() or "louvain",
        community_seed=settings.community_seed,
        # Bake the RESOLVED backend in: azure without the optional SDK
        # degrades to local here, so ingestion performs a plain registry
        # read instead of probing at read time (task 2.4).
        document_backend=resolve_document_backend(settings),
        azure_doc_intelligence_endpoint=settings.azure_doc_intelligence_endpoint,
        azure_doc_intelligence_key=settings.azure_doc_intelligence_key,
        azure_doc_intelligence_model=settings.azure_doc_intelligence_model,
        rag_profile=settings.rag_profile,
    )
