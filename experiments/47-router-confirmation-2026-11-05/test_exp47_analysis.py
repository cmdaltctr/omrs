"""Analysis and protocol tests (issue #171, points 1 and 3).

uv run --no-sync pytest experiments/47-router-confirmation-2026-11-05 -q
"""

from __future__ import annotations

import re

import pytest

import analysis
import exp47_io

LABELS = {
    "rows": [
        {"doc_id": "jone", "page": 1, "needs_ocr": False, "class": "junk"},
        {"doc_id": "jone", "page": 2, "needs_ocr": False, "class": "junk"},
        {"doc_id": "jone", "page": 3, "needs_ocr": True, "class": "junk"},
        {"doc_id": "gone", "page": 1, "needs_ocr": False, "class": "healthy"},
        {"doc_id": "gone", "page": 2, "needs_ocr": False, "class": "healthy"},
        {"doc_id": "gone", "page": 3, "needs_ocr": False, "class": "grey"},
    ]
}


def scores(ws, rows, failures=None) -> None:
    documents: dict = {}
    for doc_id, page, p_yes, rejected in rows:
        documents.setdefault(doc_id, {"rows": [], "claimed": []})["rows"].append(
            {"doc_id": doc_id, "page": page, "p_yes": p_yes, "seconds": 3.0, "rejected": rejected}
        )
    exp47_io.atomic_json(
        ws.OUTPUT / "scores_clef_router.json",
        {"documents": documents, "failures": failures or {}, "calls": {}},
    )


COMPLETE = [
    ("jone", 1, 0.05, True),
    ("jone", 2, 0.1, True),
    ("gone", 1, 0.9, False),
    ("gone", 2, 0.95, False),
    ("gone", 3, 0.5, False),
]


# ---------------------------------------------------------------- point 1: verdict


def test_complete_population_gets_a_verdict(ws, current) -> None:
    scores(ws, COMPLETE)
    summary = analysis.summarise(current, LABELS)
    assert summary["verdict"] == "PASS"
    assert summary["arms"]["clef_router"]["counts"]["junk_pages"] == 2  # the flagged page leaves


def test_missing_page_withholds_the_verdict(ws, current) -> None:
    scores(ws, COMPLETE[1:])
    summary = analysis.summarise(current, LABELS)
    assert summary["verdict"] is None
    assert "unflagged_junk: 1 of 2 items have no score" in summary["verdict_note"]


def test_failed_page_withholds_the_verdict(ws, current) -> None:
    rows = [r if r[:2] != ("gone", 2) else ("gone", 2, None, False) for r in COMPLETE]
    scores(ws, rows, failures={"gone": [2]})
    summary = analysis.summarise(current, LABELS)
    assert summary["verdict"] is None
    assert "unflagged_healthy: 1 of 2 items failed" in summary["verdict_note"]


def test_no_scores_withholds_the_verdict(ws, current) -> None:
    ws.OUTPUT.mkdir(parents=True, exist_ok=True)
    assert analysis.summarise(current, LABELS)["verdict"] is None


def test_false_rejects_fail_the_cost_gate(ws, current) -> None:
    rows = [r if r[:2] != ("gone", 1) else ("gone", 1, 0.1, True) for r in COMPLETE]
    scores(ws, rows)
    summary = analysis.summarise(current, LABELS)
    assert summary["verdict"] == "FAIL"
    g2 = next(g for g in summary["gates"] if g["id"] == "G2")
    assert g2["observed"] == 0.5 and not g2["pass"]


def test_each_document_lists_its_ocr_pages_and_share_views(ws, current) -> None:
    rows = [r if r[:2] != ("gone", 1) else ("gone", 1, 0.1, True) for r in COMPLETE]
    scores(ws, rows)
    docs = analysis.summarise(current, LABELS)["arms"]["clef_router"]["documents"]
    assert docs["gone"]["rejected_pages"] == [1] and docs["gone"]["healthy_rejected"] == 1
    assert docs["gone"]["routes_at_one_page"] and docs["gone"]["routes_at_ten_percent"]
    assert docs["gone"]["ocr_seconds"] == 38.2


def test_control_arm_rejects_nothing(ws, current) -> None:
    scores(ws, COMPLETE)
    control = analysis.summarise(current, LABELS)["arms"]["control"]
    assert control["counts"]["junk_caught"] == 0 and control["population_gaps"] == []


def test_pages_between_the_shipped_and_exact_threshold_are_listed(ws, current) -> None:
    rows = [*COMPLETE[:4], ("gone", 3, 0.1721, False)]
    scores(ws, rows)
    band = analysis.summarise(current, LABELS)["arms"]["clef_router"]
    assert band["pages_between_shipped_and_exact_threshold"] == [("gone", 3)]


def test_local_and_hosted_arms_are_compared_page_by_page(ws, current) -> None:
    scores(ws, COMPLETE)
    hosted = [r if r[:2] != ("gone", 3) else ("gone", 3, 0.1, True) for r in COMPLETE]
    hosted = [r if r[0] != "jone" else (*r[:2], 0.4, False) for r in hosted]
    (ws.OUTPUT / "scores_clef_router.json").rename(ws.OUTPUT / "keep.json")
    scores(ws, hosted)
    (ws.OUTPUT / "scores_clef_router.json").rename(ws.OUTPUT / "scores_jev_router.json")
    (ws.OUTPUT / "keep.json").rename(ws.OUTPUT / "scores_clef_router.json")
    pair = analysis.summarise(current, LABELS)["comparison"]
    assert pair["arms"] == ["clef_router", "jev_router"]
    assert pair["pages_both_scored"] == 5 and pair["agree"] == 2
    assert pair["both_reject"] == 0 and pair["neither_reject"] == 2
    assert pair["only_first_rejects"] == 2 and pair["only_second_rejects"] == 1
    assert pair["agreement_rate"] == 0.4
    assert [(d["doc_id"], d["page"], d["class"], d["rejected_by"]) for d in pair["differ"]] == [
        ("gone", 3, "grey", "jev_router"),
        ("jone", 1, "junk", "clef_router"),
        ("jone", 2, "junk", "clef_router"),
    ]


def test_comparison_is_empty_without_the_hosted_arm(ws, current) -> None:
    scores(ws, COMPLETE)
    pair = analysis.summarise(current, LABELS)["comparison"]
    assert pair["pages_both_scored"] == 0 and pair["agreement_rate"] is None


# ---------------------------------------------------------------- point 3: cleanup procedure


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, f"protocol.md has no section '{heading}'"
    return match.group(1)


@pytest.mark.parametrize("kind", sorted(exp47_io.PRIVATE_DIRS))
def test_cleanup_names_every_private_folder(kind) -> None:
    cleanup = _section((exp47_io.EXP_DIR / "protocol.md").read_text(), "8. Cleanup")
    assert f"output/.private/{kind}/" in cleanup


def test_cleanup_names_the_corpus_and_the_keep_step() -> None:
    cleanup = _section((exp47_io.EXP_DIR / "protocol.md").read_text(), "8. Cleanup")
    assert "corpus/" in cleanup and "SHA-256" in cleanup and "DATA/omrs" in cleanup
