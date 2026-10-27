"""Tests for the shared page heading-context helper (design D11, task 6a.1).

The helper computes the Markdown heading stack left open at the end of
each page document of one source, so the next page starts with it.
"""

from __future__ import annotations

import re

from llama_index.core import Document

from omrs.core.chunking.page_headings import (
    format_header_path,
    inherited_heading_stacks,
    push_heading,
)

_ATX = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


def _headings(text: str) -> list[tuple[int, str]]:
    """Return ``(level, title)`` for each ATX heading line in ``text``."""
    found = []
    for line in text.splitlines():
        match = _ATX.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def _page(text: str, page: int | None, source: str | None = "/docs/a.pdf") -> Document:
    """Build one synthetic page document."""
    metadata: dict = {}
    if page is not None:
        metadata["page"] = page
        metadata["page_label"] = str(page)
    if source is not None:
        metadata["file_path"] = source
    return Document(text=text, metadata=metadata)


def test_open_section_passes_to_next_page() -> None:
    """A page that ends inside ``# A`` / ``## B`` passes ``A > B`` on."""
    pages = [_page("# A\n\nintro\n\n## B\n\nbody\n", 1), _page("more body\n", 2)]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks[0] == ()
    assert stacks[1] == ((1, "A"), (2, "B"))
    assert format_header_path(title for _level, title in stacks[1]) == "/A/B/"


def test_same_level_heading_closes_only_that_level() -> None:
    """``## C`` on the next page closes ``B`` and keeps ``A``."""
    pages = [
        _page("# A\n\n## B\n\nbody\n", 1),
        _page("tail of B\n\n## C\n\nbody\n", 2),
        _page("tail of C\n", 3),
    ]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks[2] == ((1, "A"), (2, "C"))


def test_shallower_heading_closes_all_deeper_levels() -> None:
    """A ``# D`` on the next page closes both ``A`` and ``B``."""
    pages = [
        _page("# A\n\n## B\n\nbody\n", 1),
        _page("# D\n\nbody\n", 2),
        _page("tail of D\n", 3),
    ]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks[2] == ((1, "D"),)


def test_push_heading_pops_same_or_deeper_levels() -> None:
    """The push rule matches the Markdown parsers: pop levels >= new level."""
    stack = ((1, "A"), (2, "B"), (3, "C"))

    assert push_heading(stack, 2, "X") == ((1, "A"), (2, "X"))
    assert push_heading(stack, 4, "Y") == ((1, "A"), (2, "B"), (3, "C"), (4, "Y"))
    assert push_heading(stack, 1, "Z") == ((1, "Z"),)


def test_two_sources_never_share_a_stack() -> None:
    """Pages from two sources keep separate stacks."""
    pages = [
        _page("# A\n\nbody\n", 1, source="/docs/a.pdf"),
        _page("body of b\n", 2, source="/docs/b.pdf"),
        _page("body of a\n", 2, source="/docs/a.pdf"),
    ]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks[1] == ()
    assert stacks[2] == ((1, "A"),)


def test_out_of_order_pages_are_sorted_first() -> None:
    """Page 2 inherits from page 1 even when the reader emits page 2 first."""
    pages = [_page("body of 2\n", 2), _page("# A\n\nbody of 1\n", 1)]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks == [((1, "A"),), ()]


def test_gap_in_page_numbers_ends_the_inherited_stack() -> None:
    """A missing page means the heading context is unknown, so it resets."""
    pages = [_page("# A\n\nbody\n", 1), _page("body of 3\n", 3), _page("body of 4\n", 4)]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks == [(), (), ()]


def test_stack_carries_through_a_page_with_no_headings() -> None:
    """A page with no heading passes the open stack through unchanged."""
    pages = [_page("# A\n\nbody\n", 1), _page("\n", 2), _page("body of 3\n", 3)]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks[2] == ((1, "A"),)


def test_documents_without_page_or_source_take_no_part() -> None:
    """Only documents with an integer page and a ``file_path`` inherit."""
    pages = [
        _page("# A\n\nbody\n", 1),
        _page("no page\n", None),
        _page("no source\n", 2, source=None),
        _page("bool page\n", True),  # type: ignore[arg-type]
    ]

    stacks = inherited_heading_stacks(pages, _headings)

    assert stacks == [(), (), (), ()]


def test_single_document_source_inherits_nothing() -> None:
    """A whole-document source gets an empty stack, so it chunks as before."""
    stacks = inherited_heading_stacks([_page("# A\n\nbody\n", None)], _headings)

    assert stacks == [()]


def test_format_header_path_of_empty_stack_is_empty() -> None:
    """The formatter follows the model-token format for an empty chain."""
    assert format_header_path([]) == ""
