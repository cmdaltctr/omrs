"""Tests for the join of merged chunks that touches a display-maths fence.

Pins the scenarios of
``openspec/changes/fix-merged-chunk-maths-join/specs/retrieval-context-assembly/``:
a merge never puts text on the same line as a line that holds only ``$$``.
The texts follow the shape of the stored ``eq01`` chunks (Kingma and Welling,
arXiv 1312.6114) without copying any of the paper's prose.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.core.retrieval.assembly import assemble

_SOURCE = "src_alpha"
_VERSION = "ver_one"


class _EmptyStore:
    """Store stub; merging never reads the store."""

    def iter_filtered_documents(self, *args: Any, **kwargs: Any) -> Any:
        return iter(())


def _row(text: str, index: int) -> dict[str, Any]:
    meta = {
        "file_path": "/data/paper.pdf",
        "source_id": _SOURCE,
        "source_version": _VERSION,
        "chunk_id": f"chk_{index}",
        "source_chunk_index": index,
        "source_chunk_count": 10,
    }
    return {
        "id": f"row_{index}",
        "score": 0.5 - index / 100,
        "score_kind": "dense_cosine",
        "source": meta["file_path"],
        "page_label": None,
        "text": text,
        "metadata": meta,
        "reranked": False,
        "source_id": _SOURCE,
        "source_version": _VERSION,
        "chunk_id": meta["chunk_id"],
        "source_chunk_index": index,
        "source_chunk_count": 10,
    }


def _merge(left: str, right: str, *, chunk_overlap: int = 0) -> str:
    store: Any = _EmptyStore()
    [merged] = assemble(
        [_row(left, 0), _row(right, 1)],
        chunk_overlap=chunk_overlap,
        expand_window=0,
        store=store,
        collection="documents",
    )
    return merged["text"]


_CLOSED_BLOCK = "which can be rewritten as:\n\n$$\n\\log p(x) = a + b\n$$"


@pytest.mark.parametrize("chunk_overlap", [0, 100])
def test_closing_fence_is_followed_by_prose_on_a_new_line(chunk_overlap: int) -> None:
    merged = _merge(_CLOSED_BLOCK, "where again the term is $y$.", chunk_overlap=chunk_overlap)
    assert merged == _CLOSED_BLOCK + "\nwhere again the term is $y$."
    assert not any(line.startswith("$$") and line.strip() != "$$" for line in merged.splitlines())


@pytest.mark.parametrize("chunk_overlap", [0, 100])
def test_opening_fence_follows_prose_on_a_new_line(chunk_overlap: int) -> None:
    left = "which can be rewritten as:"
    right = "$$\nx = 1\n$$"
    assert _merge(left, right, chunk_overlap=chunk_overlap) == left + "\n" + right


def test_ordinary_join_keeps_one_space() -> None:
    left, right = "first chunk ends here.", "Second chunk starts here."
    assert _merge(left, right) == left + " " + right


def test_one_line_display_formula_keeps_one_space() -> None:
    assert _merge("the bound $$ x^2 $$", "then more text") == "the bound $$ x^2 $$ then more text"


def test_a_line_break_that_is_already_there_is_kept_as_it_is() -> None:
    left = "$$\nx\n$$\n"
    assert _merge(left, "where it holds") == left + "where it holds"
    assert _merge("text before", "\n$$\nx\n$$") == "text before\n$$\nx\n$$"


def test_overlap_removal_is_unchanged() -> None:
    left = "intro line\n\n$$\nx = 1\n$$"
    right = "$$\nx = 1\n$$ then the rest"
    merged = _merge(left, right, chunk_overlap=100)
    assert merged == "intro line\n\n$$\nx = 1\n$$ then the rest"


def test_a_join_adds_only_whitespace() -> None:
    left, right = _CLOSED_BLOCK, "where again the term is $y$."
    merged = _merge(left, right)
    assert "".join(merged.split()) == "".join((left + right).split())
    assert merged.startswith(left) and merged.endswith(right)


def test_a_fence_line_that_ends_in_a_space_or_tab_still_gets_a_line_break() -> None:
    assert _merge("a\n$$ ", "where") == "a\n$$ \nwhere"
    assert _merge("where", "$$ \nx\n$$") == "where\n$$ \nx\n$$"
    assert _merge("a\n$$\t", "where") == "a\n$$\t\nwhere"
    assert _merge("where", "$$\t\nx\n$$") == "where\n$$\t\nx\n$$"


def test_a_fence_line_with_a_break_on_the_other_side_adds_nothing() -> None:
    assert _merge("a\n$$ ", "\nwhere") == "a\n$$ \nwhere"
