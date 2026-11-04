"""Experiment 46: score the arms and write output/summary.json (protocol section 5, step 6).

Run from the repository root:

    uv run --no-sync python experiments/46-local-ocr-backends-2026-11-04/summarise.py

Reads ``pages.json``, the stored Experiment 33 control rows (arm A) and
``output/arm_<id>.jsonl`` for each arm that has run. It makes no OCR or model call. Gate
thresholds come from ``plan.json``. Statistics are basic: counts, medians and shares, no
p-values (stats level in the plan). The rank AUC for H2 is a secondary measure and enters no
gate.

Rules that the plan leaves open, fixed here before any run:

- A cut qualifies only if it keeps at least one page. No kept page is not a pass.
- A page with no confidence is never kept.
- G2 is computed once over the pages of all scripts that pass G1 (the plan's wording), and
  the same G2 verdict applies to each of those scripts.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_arm  # noqa: E402  (pure rules and file helpers shared with the runner)

OUT = HERE / "output"
CUT_GRID = [round(0.50 + 0.05 * i, 2) for i in range(10)] + [0.99]  # 0.50 ... 0.95, 0.99
GOOD_AT, BAD_BELOW = Fraction(4, 5), Fraction(1, 2)  # Experiment 39 definitions
NON_LATIN = ("arabic", "bengali", "devanagari")
ARMS = ("A", "B", "D")


# --- pure rules ----------------------------------------------------------------------------


def thresholds_from_plan(plan: dict[str, Any]) -> dict[str, float]:
    """Gate id to threshold, read from ``plan.json``."""
    return {gate["id"]: gate["threshold"] for gate in plan["gates"]}


def _at_least(value: float, threshold: float) -> bool:
    return round(value, 9) >= threshold


def _at_most(value: float, threshold: float) -> bool:
    return round(value, 9) <= threshold


def _share(part: int, whole: int) -> Fraction | None:
    return Fraction(part, whole) if whole else None


def gate_g1(recalls: list[float], thresholds: dict[str, float]) -> bool:
    """Median recall on the pages of one script."""
    return bool(recalls) and _at_least(statistics.median(recalls), thresholds["G1"])


def gate_g2(rows: list[dict[str, Any]], thresholds: dict[str, float]) -> dict[str, bool]:
    """The three G2 parts over rows with ``recall`` and ``kept``."""
    good = [r for r in rows if Fraction(str(r["recall"])) >= GOOD_AT]
    kept = [r for r in rows if r["kept"]]
    bad_kept = [r for r in kept if Fraction(str(r["recall"])) < BAD_BELOW]
    good_share = _share(sum(r["kept"] for r in good), len(good))
    bad_share = _share(len(bad_kept), len(kept))  # None when nothing is kept
    all_share = _share(len(kept), len(rows))
    return {
        "G2a": good_share is not None and good_share >= Fraction(str(thresholds["G2a"])),
        "G2b": bad_share is not None and bad_share <= Fraction(str(thresholds["G2b"])),
        "G2c": all_share is not None and all_share >= Fraction(str(thresholds["G2c"])),
    }


def gate_g3(rows: list[dict[str, Any]], thresholds: dict[str, float]) -> dict[str, bool]:
    """Latin non-regression over rows with ``stratum`` and ``diff`` (arm minus PP-OCRv6)."""
    if not rows:
        return {"G3a": False, "G3b": False}
    by_stratum: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_stratum[row["stratum"]].append(row["diff"])
    lowest = min(statistics.median(values) for values in by_stratum.values())
    overall = statistics.median(r["diff"] for r in rows)
    return {
        "G3a": _at_least(overall, thresholds["G3a"]),
        "G3b": _at_least(lowest, thresholds["G3b"]),
    }


def timed_seconds(rows: list[dict[str, Any]]) -> list[float]:
    """Seconds of the timed pages. The first pages of an arm are warm-up."""
    return [r["seconds"] for r in rows if r.get("timed")]


def gate_g4(seconds: list[float], thresholds: dict[str, float]) -> bool:
    return bool(seconds) and _at_most(statistics.median(seconds), thresholds["G4"])


def decide(table: dict[str, dict[str, dict[str, bool]]]) -> str:
    """PASS, INCONCLUSIVE or FAIL from ``table[arm][script] = {G1..G4}``."""
    verdicts = [v for scripts in table.values() for v in scripts.values()]
    if any(all(v[g] for g in ("G1", "G2", "G3", "G4")) for v in verdicts):
        return "PASS"
    if any(v["G1"] and v["G2"] and v["G4"] for v in verdicts):
        return "INCONCLUSIVE"  # only G3 fails: a script chooser would unlock it
    return "FAIL"


def choose_cut(rows: list[dict[str, Any]]) -> float | None:
    """The lowest grid cut whose kept pages are at most 0.05 bad. None if none qualifies."""
    for cut in CUT_GRID:
        kept = [r for r in rows if r["conf"] is not None and r["conf"] >= cut]
        bad = sum(Fraction(str(r["recall"])) < BAD_BELOW for r in kept)
        if kept and Fraction(bad, len(kept)) <= Fraction(1, 20):
            return cut
    return None


def leave_one_document_out(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose each document's cut on the other documents, then apply it to that document."""
    cuts: dict[str, float | None] = {}
    out: list[dict[str, Any]] = []
    for doc in sorted({r["doc"] for r in rows}):
        cut = choose_cut([r for r in rows if r["doc"] != doc])
        cuts[doc] = cut
        for row in (r for r in rows if r["doc"] == doc):
            kept = cut is not None and row["conf"] is not None and row["conf"] >= cut
            out.append({**row, "kept": kept})
    return {"rows": out, "cuts": cuts}


def registered_cut(cuts: list[float | None]) -> float | None:
    """The median of the chosen cuts, rounded half up to 0.05. Reported, not gated."""
    chosen = [c for c in cuts if c is not None]
    if not chosen:
        return None
    median = Fraction(str(round(statistics.median(chosen), 6)))
    return float(math.floor(median / Fraction(1, 20) + Fraction(1, 2)) * Fraction(1, 20))


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """Rank AUC of scores for the True label. A tie counts half. None with one class only."""
    positive = [s for s, y in zip(scores, labels, strict=True) if y]
    negative = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not positive or not negative:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


# --- data ----------------------------------------------------------------------------------


def _arm_rows(arm: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """One scored row per page for the arm, or None when the arm has not run."""
    if arm == "A":
        stored = {(r["doc_id"], r["page"]): r for r in run_arm.stored_rows()}
        raw = [
            {
                "doc": p["doc"],
                "page": p["page"],
                "text": run_arm.stored_text(p["doc"], p["page"]),
                "page_confidence": stored[(p["doc"], p["page"])]["confidence"],
                "seconds": stored[(p["doc"], p["page"])]["doc_seconds_share"],
                "timed": False,  # the control's seconds are a document average (limit 6)
                "error": None,
            }
            for p in pages
        ]
    else:
        path = OUT / f"arm_{arm.lower()}.jsonl"
        if not path.is_file():
            return None
        by_key = {
            (r["doc"], r["page"]): r
            for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x)
        }
        raw = [by_key[k] for p in pages if (k := (p["doc"], p["page"])) in by_key]
    meta = {(p["doc"], p["page"]): p for p in pages}
    rows = []
    for r in raw:
        page = meta[(r["doc"], r["page"])]
        reference = run_arm.reference_tokens(r["doc"], r["page"])
        rows.append(
            {
                "doc": r["doc"],
                "page": r["page"],
                "script": page["script"],
                "stratum": page["stratum"],
                "recall": run_arm.page_recall(r["text"], reference),
                "recall_dots": _recall_dots(r["text"], r["doc"], r["page"]),
                "conf": r["page_confidence"],
                "conf_min_long": r.get("min_conf_long_lines"),
                "conf_share": r.get("share_confident_chars"),
                "seconds": r["seconds"],
                "timed": r["timed"],
                "error": r["error"],
            }
        )
    return rows


def _recall_dots(text: str, doc: str, page: int) -> float | None:
    """Recall of the arm text against the stored dots.mocr text, where that text exists."""
    try:
        path = run_arm.find(f"{run_arm.EXP37}/output/dots-mocr") / doc / f"p{page:03d}.md"
    except run_arm.Stop:
        return None
    if not path.is_file():
        return None
    return run_arm.page_recall(text, run_arm.tokens(path.read_text(encoding="utf-8")))


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _score_arm(arm: str, rows: list[dict[str, Any]], control: dict, th: dict) -> dict[str, Any]:
    """Gates, cuts and tables for one arm."""
    per_script = {
        s: [r["recall"] for r in rows if r["script"] == s]
        for s in NON_LATIN
        if any(r["script"] == s for r in rows)
    }
    g1 = {s: gate_g1(values, th) for s, values in per_script.items()}
    folded = leave_one_document_out(rows)
    passing = [r for r in folded["rows"] if g1.get(r["script"])]
    g2 = gate_g2(passing, th) if passing else {"G2a": False, "G2b": False, "G2c": False}
    latin = [
        {"stratum": r["stratum"], "diff": r["recall"] - control[(r["doc"], r["page"])]}
        for r in rows
        if r["script"] == "latin"
    ]
    g3 = gate_g3(latin, th)
    diffs: dict[str, list[float]] = defaultdict(list)
    for item in latin:
        diffs[item["stratum"]].append(item["diff"])
    g3_values = {  # reported values behind the two G3 booleans
        "overall_median_diff": _median([item["diff"] for item in latin]),
        "stratum_median_diff": {s: _median(v) for s, v in sorted(diffs.items())},
    }
    stopped = (OUT / f"arm_{arm.lower()}.stopped.json").is_file()
    g4 = gate_g4(timed_seconds(rows), th) and not stopped
    table = {
        s: {"G1": g1[s], "G2": g1[s] and all(g2.values()), "G3": all(g3.values()), "G4": g4}
        for s in g1
    }
    graded = [r for r in rows if r["conf"] is not None]
    return {
        "pages": len(rows),
        "errors": sum(1 for r in rows if r["error"]),
        "median_recall_by_script": {s: _median(v) for s, v in per_script.items()},
        "median_recall_vs_dots_by_script": {
            s: _median(
                [
                    r["recall_dots"]
                    for r in rows
                    if r["script"] == s and r["recall_dots"] is not None
                ]
            )
            for s in per_script
        },
        "gates": {"G1": g1, **g2, **g3, "G4": g4, "stopped_by_rule": stopped},
        "verdict_by_script": table,
        "g3_values": g3_values,
        "loo_cuts": folded["cuts"],
        "registered_cut": registered_cut(list(folded["cuts"].values())),
        "g2_counts": {
            "pages": len(passing),
            "good": sum(Fraction(str(r["recall"])) >= GOOD_AT for r in passing),
            "kept": sum(r["kept"] for r in passing),
            "kept_bad": sum(r["kept"] and Fraction(str(r["recall"])) < BAD_BELOW for r in passing),
        },
        "median_seconds_timed": _median(timed_seconds(rows)),
        "auc_recall_ge_0_8": {
            name: auc(
                [r[name] for r in graded if r[name] is not None],
                [r["recall"] >= 0.8 for r in graded if r[name] is not None],
            )
            for name in ("conf", "conf_min_long", "conf_share")
        },
        "rows": folded["rows"],
    }


def main() -> int:
    plan = run_arm.load_plan()
    th = thresholds_from_plan(plan)
    pages = json.loads(run_arm.PAGES.read_text(encoding="utf-8"))["pages"]
    scored = {arm: _arm_rows(arm, pages) for arm in ARMS}
    control = {(r["doc"], r["page"]): r["recall"] for r in scored["A"] or []}
    summary: dict[str, Any] = {"thresholds": th, "arms": {}, "not_run": []}
    for arm in ARMS:
        rows = scored[arm]
        if rows is None:
            summary["not_run"].append(arm)
        elif arm != "A":
            summary["arms"][arm] = _score_arm(arm, rows, control, th)
    if scored["A"]:
        a = scored["A"]
        summary["control_A"] = {
            "median_recall_by_script": {
                s: _median([r["recall"] for r in a if r["script"] == s])
                for s in (*NON_LATIN, "latin")
            },
            "median_recall_by_stratum": {
                s: _median([r["recall"] for r in a if r["stratum"] == s])
                for s in sorted({r["stratum"] for r in a if r["stratum"]})
            },
            "rows": a,
        }
    table = {arm: res["verdict_by_script"] for arm, res in summary["arms"].items()}
    summary["outcome"] = decide(table) if table else None
    run_arm.write_json(OUT / "summary.json", summary)
    arms, not_run = sorted(summary["arms"]), summary["not_run"]
    print(f"outcome {summary['outcome']}  arms {arms}  not run {not_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
