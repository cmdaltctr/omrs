"""Experiment 45: summarise output/verdicts.json into output/summary.json (step S5).

Counts only (stats level `basic`): each quantity comes from a fixed set of pages, so there
is no interval and no p-value. Gates and the rule come from plan.json, never from a value
chosen after the run.

    uv run --no-sync python experiments/45-non-latin-script-routing-2026-11-04/summarise.py
"""

from __future__ import annotations

import json
import operator
import os
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
OUT = HERE / "output"
DATA = json.loads((OUT / "verdicts.json").read_text(encoding="utf-8"))
OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq}
CLASSES = ("non_latin", "unclassified", "latin")


def label(verdict: bool | None) -> str:
    return "no_verdict" if verdict is None else ("non_latin" if verdict else "latin_verdict")


def per_doc(rows: list[dict]) -> dict[str, dict[str, dict[str, int]]]:
    """doc -> page class -> verdict label -> count."""
    table: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        table[row["doc_id"]][row["page_class"]][label(row["verdict"])] += 1
    return {doc: {cls: dict(c) for cls, c in sorted(by.items())} for doc, by in sorted(table.items())}


def totals(rows: list[dict], page_class: str) -> dict[str, int]:
    return dict(Counter(label(r["verdict"]) for r in rows if r["page_class"] == page_class))


def main() -> None:
    flag, local, engine = DATA["flag_rows"], DATA["local_rows"], DATA["engine_rows"]

    # (a) point 1: flagged pages, verdict on the text items before OCR.
    a = {
        "per_document": per_doc(flag),
        "totals_by_class": {cls: totals(flag, cls) for cls in CLASSES},
        "non_latin_verdicts": sum(1 for r in flag if r["verdict"] is True),
        "flagged_pages": len(flag),
        "flagged_pages_with_a_text_item": sum(1 for r in flag if r["text_items"] > 0),
    }

    # (b) point 2: stored local OCR text.
    b = {
        "per_document": per_doc(local),
        "totals_by_class": {cls: totals(local, cls) for cls in CLASSES},
    }

    # (c) false positives on Latin pages.
    latin_flag = [r for r in flag if r["page_class"] == "latin"]
    latin_local = [r for r in local if r["page_class"] == "latin"]
    latin_engine = [r for r in engine if r["page_class"] == "latin"]
    c1 = [r for r in latin_flag if r["verdict"] is True]
    c2 = [r for r in latin_local if r["verdict"] is True]
    c3 = [r for r in latin_engine if r["verdict"] is True]
    c = {
        "c1_flagged_latin_pages_non_latin_verdict": len(c1),
        "c2_stored_latin_rows_non_latin_verdict": len(c2),
        "c": len(c1) + len(c2),
        "latin_flagged_pages": len(latin_flag),
        "latin_flagged_pages_with_a_verdict": sum(1 for r in latin_flag if r["verdict"] is not None),
        "latin_stored_rows": len(latin_local),
        "latin_stored_rows_with_a_verdict": sum(1 for r in latin_local if r["verdict"] is not None),
        "c3_not_gated_engine_text_latin_pages": {
            "pages": len(latin_engine),
            "with_a_verdict": sum(1 for r in latin_engine if r["verdict"] is not None),
            "non_latin_verdicts": len(c3),
            "listed": [[r["doc_id"], r["page"]] for r in c3],
        },
        "c1_listed": [[r["doc_id"], r["page"]] for r in c1],
        "c2_listed": [[r["doc_id"], r["page"]] for r in c2],
    }

    # (d) local seconds saved by `always` on the 129 non-Latin pages.
    class_rows = [r for r in local if r["page_class"] == "non_latin"]
    seconds: dict[str, float] = defaultdict(float)
    for row in class_rows:
        seconds[row["doc_id"]] += row["doc_seconds_share"]
    d = {
        "per_document_seconds": {doc: round(v, 3) for doc, v in sorted(seconds.items())},
        "total_seconds_129_pages": round(sum(r["doc_seconds_share"] for r in class_rows), 3),
        "total_seconds_without_timed_out_documents": round(
            sum(r["doc_seconds_share"] for r in class_rows if not r["doc_over_soft_timeout"]), 3
        ),
        "latin_class_stored_rows_seconds": round(
            sum(r["doc_seconds_share"] for r in latin_local), 3
        ),
        "latin_class_stored_rows": len(latin_local),
    }

    # (e) kept by the 0.9 cut and escalated by `detect`.
    kept = [r for r in class_rows if r["kept_by_cut"]]
    escalated_only_by_detect = [r for r in kept if r["verdict"] is True]
    e = {
        "e": len(escalated_only_by_detect),
        "e0_kept_by_cut_any_verdict": len(kept),
        "non_latin_class_rows": len(class_rows),
        "escalated_by_shipped_reasons_of_129": len(class_rows) - len(kept),
        "reasons_among_129": dict(Counter(reason for r in class_rows for reason in r["reasons"])),
        "confidence_min_max_of_129": [
            min(r["confidence"] for r in class_rows if r["confidence"] is not None),
            max(r["confidence"] for r in class_rows if r["confidence"] is not None),
        ],
        "kept_rows": [
            {"doc": r["doc_id"], "page": r["page"], "confidence": r["confidence"], "verdict": r["verdict"]}
            for r in kept
        ],
        "verdicts_of_129_non_latin_class": dict(Counter(label(r["verdict"]) for r in class_rows)),
    }

    # Cross-check of the class on engine text (S4).
    engine_check = {
        "non_latin_class_pages": sum(1 for r in engine if r["page_class"] == "non_latin"),
        "non_latin_class_with_non_latin_verdict": sum(
            1 for r in engine if r["page_class"] == "non_latin" and r["verdict"] is True
        ),
    }

    gate_values = {
        "G1": e["e"],
        "G2": c["c"],
    }
    gates = {}
    for gate in PLAN["gates"]:
        value = gate_values[gate["id"]]
        gates[gate["id"]] = {
            "metric": gate["metric"],
            "value": value,
            "op": gate["op"],
            "threshold": gate["threshold"],
            "pass": bool(OPS[gate["op"]](value, gate["threshold"])),
        }
    passed = all(g["pass"] for g in gates.values())
    summary = {
        "experiment_id": PLAN["experiment_id"],
        "stats": PLAN["stats"],
        "detector": DATA["meta"]["detector"],
        "cut": DATA["meta"]["cut"],
        "pdf_inspector": DATA["meta"]["pdf_inspector"],
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "e": e,
        "engine_text_class_check": engine_check,
        "gates": gates,
        "rule_outcome": (
            "PASS: propose `detect` as the default in its own change and ADR"
            if passed
            else "FAIL for the default: keep `off`"
        ),
        "outcome_row": ("G1 " + ("pass" if gates["G1"]["pass"] else "fail")
                        + ", G2 " + ("pass" if gates["G2"]["pass"] else "fail")),
        "hypotheses": {
            "H1": "supported" if gates["G1"]["pass"] else "not supported",
            "H2": "supported" if gates["G2"]["pass"] else "not supported",
        },
    }
    tmp = OUT / "summary.json.tmp"
    tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, OUT / "summary.json")
    print(json.dumps({k: summary[k] for k in ("gates", "rule_outcome", "outcome_row")}, indent=2))


if __name__ == "__main__":
    main()
