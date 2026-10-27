"""Markdown chunking strategy (heading-aware, small-chunk dropping, heading prepend).

Experiment 6c recovery hooks: heading metadata propagation, optional
heading-prepend, and optional small-chunk dropping.  Extracted from the
original ``ingestion.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core.schema import MetadataMode

from .page_headings import (
    HeadingStack,
    format_header_path,
    inherited_heading_stacks,
    push_heading,
)

logger = logging.getLogger(__name__)

# The heading rule of LlamaIndex ``MarkdownNodeParser.get_nodes_from_node``.
_PARSER_HEADING = re.compile(r"^(#+)\s(.*)")


def ensure_heading_metadata(nodes: list) -> None:
    """Defensively copy source heading metadata onto emitted child nodes.

    Experiment 6c recovery hook.  LlamaIndex splitters can emit child nodes
    whose own metadata omits heading information even though their
    ``source_node`` still has it.  This idempotently preserves that metadata
    for evidence/section evaluators and downstream search results.

    Args:
        nodes: Nodes emitted by the Markdown parser / splitter pipeline.
    """
    for node in nodes:
        source_node = getattr(node, "source_node", None)
        source_meta = getattr(source_node, "metadata", {}) if source_node else {}
        header_path = source_meta.get("header_path") or source_meta.get("heading_path")
        if header_path:
            node.metadata.setdefault("header_path", header_path)


def apply_heading_prepend(nodes: list, heading_prepend: bool = False) -> None:
    """Optionally prepend heading path to Markdown chunk text.

    Experiment 6c recovery knob controlled by ``MARKDOWN_HEADING_PREPEND``.
    Disabled by default.  When enabled, heading context becomes part of the
    embedded text while a double-prepend guard keeps repeated processing safe.

    Args:
        nodes: Markdown nodes after heading metadata propagation.
        heading_prepend: Whether prepending is enabled, from the injected
            settings (``chunking.markdown_heading_prepend``).
    """
    if not heading_prepend:
        return
    for node in nodes:
        header_path = node.metadata.get("header_path") or node.metadata.get("heading_path")
        if not header_path:
            continue
        prefix = f"[{header_path}] "
        text = getattr(node, "text", "")
        if text.startswith(prefix):
            continue
        node.text = prefix + text


def drop_small_markdown_chunks(
    nodes: list,
    chunk_size: int,
    min_chunk_fraction: float = 0.0,
    tokenizer: Any | None = None,
) -> list:
    """Optionally drop tiny Markdown chunks before embedding.

    Experiment 6c recovery knob controlled by
    ``MARKDOWN_MIN_CHUNK_FRACTION``. Disabled by default. The model-aware
    path uses the injected tokenizer; the legacy path keeps the character
    estimate used in the 6b/6c chunk-size reports.

    Args:
        nodes: Markdown nodes to filter.
        chunk_size: Effective Markdown chunk size for this ingestion run.
        min_chunk_fraction: Minimum-size floor as a fraction of chunk_size,
            from the injected settings. ``<= 0`` disables the filter.
        tokenizer: Optional resolved model tokenizer for exact token counting.

    Returns:
        The original node list when disabled, otherwise only nodes meeting
        the configured minimum estimated size.
    """
    if min_chunk_fraction <= 0:
        return nodes
    if tokenizer is None:
        minimum_chars = int(chunk_size * 4 * min_chunk_fraction)
        kept = [node for node in nodes if len(getattr(node, "text", "")) >= minimum_chars]
    else:
        minimum_tokens = chunk_size * min_chunk_fraction
        kept = [
            node
            for node in nodes
            if len(tokenizer.encode(getattr(node, "text", "")).ids) >= minimum_tokens
        ]
    dropped = len(nodes) - len(kept)
    if dropped:
        logger.info("Dropped %d Markdown chunk(s) below min-size floor", dropped)
    return kept


def parse_markdown_sections(documents: list) -> list:
    """Split Markdown documents into heading sections with ``MarkdownNodeParser``.

    A source read as page documents keeps the heading context of earlier
    pages (design D11): a section that continues onto the next page gets
    the ``header_path`` that whole-document parsing gives it. Documents
    without page provenance parse exactly as before.

    Args:
        documents: LlamaIndex documents containing Markdown.

    Returns:
        One node per heading section, in document order.
    """
    nodes = MarkdownNodeParser().get_nodes_from_documents(documents)
    stacks = inherited_heading_stacks(documents, _parser_headings)
    for document, open_stack in zip(documents, stacks, strict=True):
        if not open_stack:
            continue
        sections = [node for node in nodes if node.ref_doc_id == document.doc_id]
        text = document.get_content(metadata_mode=MetadataMode.NONE)
        _apply_inherited_paths(sections, _parser_headings(text), open_stack)
    return nodes


def _parser_headings(text: str) -> list[tuple[int, str]]:
    """Return the headings ``MarkdownNodeParser`` finds, as ``(level, title)``.

    This mirrors the parser: lines split on ``\\n``, a line starting with
    a code fence toggles code mode, and no heading counts inside code.
    """
    headings: list[tuple[int, str]] = []
    code_block = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            code_block = not code_block
            continue
        match = None if code_block else _PARSER_HEADING.match(line)
        if match:
            headings.append((len(match.group(1)), match.group(2)))
    return headings


def _apply_inherited_paths(
    sections: list,
    headings: list[tuple[int, str]],
    open_stack: HeadingStack,
) -> None:
    """Rewrite the ``header_path`` of one page's sections from an open stack.

    The parser gives each heading section the path of the headings above
    it, and emits one section per heading plus one for any text before the
    first heading. The page's sections are matched to its headings in that
    order.

    Args:
        sections: The page's sections, in order.
        headings: The page's headings from :func:`_parser_headings`.
        open_stack: The headings left open by the previous page.
    """
    if len(sections) == len(headings) + 1:
        sections[0].metadata["header_path"] = _parent_path(open_stack)
        sections = sections[1:]
    elif len(sections) != len(headings):
        logger.warning(
            "Markdown page sections (%d) do not match its headings (%d); "
            "keeping per-page header paths",
            len(sections),
            len(headings),
        )
        return
    stack = open_stack
    for section, (level, title) in zip(sections, headings, strict=True):
        stack = push_heading(stack, level, title)
        section.metadata["header_path"] = _parent_path(stack)


def _parent_path(stack: HeadingStack) -> str:
    """Return the parser-format path of the headings above the innermost one."""
    return format_header_path(title for _level, title in stack[:-1]) or "/"
