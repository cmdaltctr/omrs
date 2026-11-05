"""Labelling tests: the imported token rule, frozen classes and the freeze order.

uv run --no-sync pytest experiments/47-router-confirmation-2026-11-05 -q
"""

from __future__ import annotations

import pytest
from conftest import frozen_labels, prepared

import exp47_io
import label_pages

THRESHOLDS = {"junk_below": 0.5, "healthy_at": 0.8, "min_reference_tokens": 10}
REFERENCE = "the quick brown fox jumps over the lazy dog near the river bank today"


@pytest.fixture
def rule(current):
    path = exp47_io.frozen_file(current, label_pages.TOKEN_RULE_ITEM)
    return exp47_io.load_module(path, "exp33_build_labels")


@pytest.mark.parametrize(
    ("text", "reference", "label"),
    [
        (REFERENCE, REFERENCE, "healthy"),
        ("INT , L/ NUI a NS SRA", REFERENCE, "junk"),
        ("the quick brown fox jumps over the lazy", REFERENCE, "grey"),
        ("", REFERENCE, "excluded"),
        (REFERENCE, "too short", "excluded"),
        (REFERENCE, None, "excluded"),
    ],
)
def test_classes_follow_the_frozen_rule(rule, text, reference, label) -> None:
    assert label_pages.classify(text, reference, rule, THRESHOLDS)["class"] == label


def test_labels_use_the_shipped_text_and_the_local_reference(ws, current) -> None:
    inputs = prepared(ws)
    pages = {}
    for doc_id, doc in inputs["documents"].items():
        for row in doc["rows"]:
            text = ws.texts[f"{doc_id}.pdf"][row["page"] - 1][0]
            reference = REFERENCE if doc_id == "jone" else text
            path = exp47_io.private_path("references", doc_id, f"p{row['page']:03d}.md")
            path.write_text(reference, encoding="utf-8")
            pages[f"{doc_id}:{row['page']}"] = {
                "status": "ok",
                "sha256": exp47_io.text_sha256(reference),
            }
    exp47_io.atomic_json(ws.REFERENCE_STATE, {"pages": pages})
    payload = label_pages.labels(current)
    classes = {(r["doc_id"], r["page"]): r["class"] for r in payload["rows"]}
    assert classes == {
        ("jone", 1): "junk",
        ("jone", 2): "junk",
        ("gone", 1): "healthy",
        ("gone", 2): "healthy",
    }
    assert "INT , L/" not in ws.LABELS.read_text()
    review = exp47_io.read_json(ws.LABEL_REVIEW)
    assert {(p["doc_id"], p["page"]) for p in review["pages"]} >= {("jone", 1), ("jone", 2)}


def test_labels_refuse_once_a_router_score_exists(ws, current) -> None:
    (ws.OUTPUT).mkdir(parents=True, exist_ok=True)
    (ws.OUTPUT / "scores_clef_router.json").write_text("{}")
    with pytest.raises(SystemExit, match="labels are frozen"):
        label_pages.labels(current)
    with pytest.raises(SystemExit, match="labels are frozen"):
        label_pages.references(resume=True)


def test_review_sample_is_seeded() -> None:
    rows = [{"doc_id": "d", "page": n, "class": "healthy"} for n in range(1, 30)]
    rows.append({"doc_id": "d", "page": 40, "class": "junk"})
    first = label_pages.review_sample(rows, 5, 47)
    assert first == label_pages.review_sample(rows, 5, 47)
    assert (
        len(first) == 6 and {"doc_id": "d", "page": 40, "class": "junk", "verdict": None} in first
    )


def test_labels_frozen_needs_a_complete_review_and_a_passing_set_check(ws, current) -> None:
    prepared(ws)
    frozen_labels(ws)
    assert label_pages.labels_frozen(current, clean=lambda p: True) == []
    assert label_pages.labels_frozen(current, clean=lambda p: False)[0].endswith("not committed")
    exp47_io.atomic_json(ws.SET_CHECK, {"pass": False})
    assert any(
        "INCONCLUSIVE" in r for r in label_pages.labels_frozen(current, clean=lambda p: True)
    )


def test_set_check_counts_only_unflagged_pages() -> None:
    rows = [
        {"doc_id": "a", "page": 1, "class": "junk", "needs_ocr": True},
        {"doc_id": "a", "page": 2, "class": "junk", "needs_ocr": False},
        {"doc_id": "b", "page": 1, "class": "healthy", "needs_ocr": False},
    ]
    check = label_pages.set_check(rows, {"unflagged_junk_pages": 2})
    assert check["found"]["unflagged_junk_pages"] == 1 and not check["pass"]
