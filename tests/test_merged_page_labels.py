"""Tests for the page labels of merged search rows and their citations.

Pins the scenarios of
``openspec/changes/add-merged-result-page-labels/specs/`` for the
``retrieval-context-assembly`` and ``grounded-answer-synthesis``
capabilities: a merged row lists every page it spans in ``page_labels``,
and evidence rows and citations carry that list unchanged.
"""

from __future__ import annotations

from typing import Any

from omrs.core.answer.citations import build_citations
from omrs.core.answer.evidence import evidence_rows
from omrs.core.retrieval.assembly import assemble

_SOURCE = "src_alpha"
_VERSION = "ver_one"


class _EmptyStore:
    """Store stub; merging never reads the store."""

    def iter_filtered_documents(self, *args: Any, **kwargs: Any) -> Any:
        return iter(())


def _row(index: int, page: str | None, *, page_on_row: bool = True) -> dict[str, Any]:
    """Build one ranked row of chunk ``index`` on page ``page``."""
    meta: dict[str, Any] = {
        "file_path": "/data/report.pdf",
        "source_id": _SOURCE,
        "source_version": _VERSION,
        "chunk_id": f"chk_{index}",
        "source_chunk_index": index,
        "source_chunk_count": 10,
    }
    if page is not None:
        meta["page_label"] = page
    return {
        "id": f"row_{index}",
        "score": 0.5 - index / 100,
        "score_kind": "dense_cosine",
        "source": meta["file_path"],
        "page_label": page if page_on_row else None,
        "text": f"chunk {index} unique words w{index}",
        "metadata": meta,
        "reranked": False,
        "source_id": _SOURCE,
        "source_version": _VERSION,
        "chunk_id": meta["chunk_id"],
        "source_chunk_index": index,
        "source_chunk_count": 10,
    }


def _assemble(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store: Any = _EmptyStore()
    return assemble(rows, chunk_overlap=0, expand_window=0, store=store, collection="documents")


# ── retrieval-context-assembly ────────────────────────────────────────


def test_merged_row_spanning_two_pages_lists_both() -> None:
    [merged] = _assemble([_row(4, "5"), _row(5, "6")])
    assert merged["page_labels"] == ["5", "6"]
    assert merged["page_label"] == "5"


def test_merged_row_on_one_page_lists_it_once() -> None:
    [merged] = _assemble([_row(1, "12"), _row(2, "12"), _row(3, "12")])
    assert merged["page_labels"] == ["12"]


def test_merged_row_without_page_labels_has_no_list() -> None:
    [merged] = _assemble([_row(1, None), _row(2, None)])
    assert "page_labels" not in merged


def test_unmerged_row_has_no_list() -> None:
    [row] = _assemble([_row(3, "3")])
    assert "page_labels" not in row
    assert row["page_label"] == "3"


def test_label_falls_back_to_metadata() -> None:
    [merged] = _assemble([_row(4, "5"), _row(5, "6", page_on_row=False)])
    assert merged["page_labels"] == ["5", "6"]


def test_labels_keep_chunk_order_not_numeric_order() -> None:
    [merged] = _assemble([_row(4, "x"), _row(5, "1")])
    assert merged["page_labels"] == ["x", "1"]


# ── grounded-answer-synthesis ─────────────────────────────────────────


def test_citation_of_merged_row_carries_page_labels() -> None:
    [merged] = _assemble([_row(4, "5"), _row(5, "6")])
    evidence = evidence_rows([merged])
    assert evidence[0]["page_labels"] == ["5", "6"]
    [citation] = build_citations(evidence, [1])
    assert citation["page_labels"] == ["5", "6"]


def test_citation_of_single_chunk_has_no_page_labels() -> None:
    [row] = _assemble([_row(3, "3")])
    evidence = evidence_rows([row])
    assert "page_labels" not in evidence[0]
    [citation] = build_citations(evidence, [1])
    assert "page_labels" not in citation


# ── HTTP contract ─────────────────────────────────────────────────────


def test_contract_declares_optional_page_labels() -> None:
    from pathlib import Path

    import yaml

    contract = Path(__file__).parents[1] / "src/omrs/transports/api/openapi.yaml"
    schemas = yaml.safe_load(contract.read_text(encoding="utf-8"))["components"]["schemas"]
    for name in ("SearchResult", "AnswerCitation", "AnswerEvidence"):
        field = schemas[name]["properties"].get("page_labels")
        assert field == {**field, "type": "array", "items": {"type": "string"}}, name
        assert "page_labels" not in schemas[name].get("required", []), name
