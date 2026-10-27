"""Heading context that carries across the page documents of one source.

A PDF reader can emit one document per page. The Markdown chunkers build
``header_path`` per document from an empty heading stack, so the first
chunks of a page would lose a section heading opened on an earlier page.
This module computes, for each page document, the heading stack left open
at the end of the previous page (design D11). Both Markdown chunking paths
use it, so they cannot disagree.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from llama_index.core.schema import MetadataMode

HeadingStack = tuple[tuple[int, str], ...]
"""Open headings as ``(level, title)`` pairs, outermost first."""

HeadingReader = Callable[[str], Iterable[tuple[int, str]]]
"""Return the ``(level, title)`` of each heading in a text, in order."""


def push_heading(stack: HeadingStack, level: int, title: str) -> HeadingStack:
    """Open one heading on a stack.

    The heading closes every open heading of the same or a deeper level,
    which is the rule both Markdown chunkers apply inside one document.

    Args:
        stack: The open headings before this heading.
        level: The heading level (1 for ``#``).
        title: The heading title.

    Returns:
        The open headings after this heading.
    """
    kept = list(stack)
    while kept and kept[-1][0] >= level:
        kept.pop()
    kept.append((level, title))
    return tuple(kept)


def format_header_path(titles: Iterable[str]) -> str:
    """Format heading titles as a slash-delimited ``header_path``.

    Args:
        titles: Heading titles, outermost first.

    Returns:
        ``"/A/B/"`` for titles ``A`` and ``B``, or ``""`` for no titles.
    """
    joined = "/".join(titles)
    return f"/{joined}/" if joined else ""


def page_number(document: Any) -> int | None:
    """Return the integer ``page`` metadata of a document, or ``None``."""
    page = getattr(document, "metadata", {}).get("page")
    if isinstance(page, int) and not isinstance(page, bool):
        return page
    return None


def source_key(document: Any) -> str | None:
    """Return the ``file_path`` metadata that names a document's source."""
    source = getattr(document, "metadata", {}).get("file_path")
    return source if isinstance(source, str) and source else None


def inherited_heading_stacks(
    documents: Sequence[Any],
    read_headings: HeadingReader,
) -> list[HeadingStack]:
    """Return the heading stack open at the start of each document.

    Source identity: a document takes part only when its metadata has an
    integer ``page`` and a non-empty ``file_path``. Every PDF reader sets
    ``file_path`` on each page document at read time, so it is present when
    the chunker runs. The ``source_id`` key is stamped later in the pipeline
    and is not available here. Documents with the same ``file_path`` form
    one source; a stack never passes between sources.

    Within one source, pages are taken in ``page`` order (the input order
    breaks ties). Each page starts with the stack left open at the end of
    the previous page. A gap in page numbers, such as a failed or
    worker-read page, ends the inherited stack. A document without page
    provenance, such as a whole-document read, gets an empty stack, so it
    chunks exactly as before.

    The result follows the input order; the caller keeps its own order.
    A fenced code block left open at a page end is not carried over.

    Args:
        documents: The documents of one chunking call.
        read_headings: The heading detector of the calling chunker, so the
            stack follows the same heading rules as that chunker.

    Returns:
        One stack per input document, in input order.
    """
    stacks: list[HeadingStack] = [() for _ in documents]
    by_source: dict[str, list[tuple[int, int]]] = {}
    for index, document in enumerate(documents):
        page = page_number(document)
        source = source_key(document)
        if page is not None and source is not None:
            by_source.setdefault(source, []).append((page, index))

    for pages in by_source.values():
        open_stack: HeadingStack = ()
        previous: int | None = None
        for page, index in sorted(pages):
            if previous is None or page - previous > 1:
                open_stack = ()
            stacks[index] = open_stack
            text = documents[index].get_content(metadata_mode=MetadataMode.NONE)
            for level, title in read_headings(text):
                open_stack = push_heading(open_stack, level, title)
            previous = page
    return stacks
