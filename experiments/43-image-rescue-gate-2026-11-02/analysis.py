"""Tasks 3.1 and 3.4: fit the D2 thresholds and summarise every arm.

    uv run --no-sync python analysis.py --fit clef_image   # print the threshold only
    uv run --no-sync python analysis.py                    # write output/summary.json

Page level: junk pages caught, healthy pages flagged. Document level: routes under
the 10% rule and the one-page rule, with prior routes kept, flags counted only on
rescued documents, and the OCR cost of each newly routed usable document.
"""

from __future__ import annotations

import argparse
from typing import Any

from exp43_io import EXP33, EXP38, JUNK_DOCS, OUTPUT, atomic_json, load_module, plan, read_json

Key = tuple[str, int]
ARMS = ("control", "word_check", "clef_image", "jev_image")
FIT_PAGES = 561
DOTS_SECONDS_PER_PAGE = 38.2
PRICE_PER_INPUT_TOKEN = 42e-9


def flagged(scores: dict[Key, float], threshold: float | None) -> set[Key]:
    """Pages whose score is strictly below the threshold (control: none)."""
    if threshold is None:
        return set()
    return {key for key, value in scores.items() if value < threshold}


def route(
    documents: list[dict],
    labels: dict[str, str],
    flags: set[Key],
    population: set[Key],
    rule: str,
) -> dict[str, dict]:
    """Route each document; only pages of rescued documents in *population* can flag."""
    result = {}
    for doc in documents:
        doc_id, pages = doc["doc_id"], doc["page_count"]
        rescued = doc["extraction_fallback_backend"] == "liteparse"
        count = sum(1 for key in flags & population if key[0] == doc_id) if rescued else 0
        prior = bool(doc["ocr_required"])
        hit = count >= 1 if rule == "one_page" else count / pages >= 0.10
        routed = prior or hit
        new_usable = routed and not prior and labels[doc_id] == "usable"
        result[doc_id] = {
            "pages": pages,
            "rescued": rescued,
            "flagged_pages": count,
            "prior_routed": prior,
            "routed": routed,
            "label": labels[doc_id],
            "newly_routed_usable": new_usable,
            "ocr_cost_pages": pages if new_usable else 0,
        }
    return result


def pass_rule(routing: dict[str, dict]) -> dict[str, Any]:
    """Part 1: rf06 and rf07 route. Part 2: no usable document is newly routed."""
    usable = sorted(d for d, row in routing.items() if row["newly_routed_usable"])
    part_1 = all(routing[d]["routed"] for d in JUNK_DOCS)
    cost = sum(routing[d]["ocr_cost_pages"] for d in usable)
    return {
        "part_1_rf06_rf07_routed": part_1,
        "rf06_routed": routing["rf06"]["routed"],
        "rf07_routed": routing["rf07"]["routed"],
        "part_2_no_usable_newly_routed": not usable,
        "usable_newly_routed": usable,
        "ocr_cost_pages": cost,
        "ocr_cost_seconds": round(cost * DOTS_SECONDS_PER_PAGE, 1),
        "pass": part_1 and not usable,
    }


def page_metrics(classes: dict[Key, str], flags: set[Key], scored: set[Key]) -> dict:
    """Junk pages caught (all, and in rf06 and rf07) and healthy pages flagged."""
    junk = [k for k, c in classes.items() if c == "junk"]
    healthy = [k for k, c in classes.items() if c == "healthy"]
    return {
        "junk_pages": len(junk),
        "junk_caught": sum(k in flags for k in junk),
        "junk_rf06_rf07_pages": sum(k[0] in JUNK_DOCS for k in junk),
        "junk_rf06_rf07_caught": sum(k in flags and k[0] in JUNK_DOCS for k in junk),
        "healthy_pages": len(healthy),
        "healthy_flagged": sum(k in flags for k in healthy),
        "junk_unscored": sum(k not in scored for k in junk),
        "healthy_unscored": sum(k not in scored for k in healthy),
    }


def fit_threshold(rows: list[dict]) -> float:
    """Experiment 38 equal-cost rule on the fit pages of one image arm."""
    stats = load_module(EXP38 / "signal_stats.py", "exp38_signal_stats")
    fit = [r for r in rows if r["phase"] == "fit"]
    if len(fit) != FIT_PAGES or any(r["doc_id"] in JUNK_DOCS for r in fit):
        raise SystemExit(f"fit needs {FIT_PAGES} pages outside rf06 and rf07, got {len(fit)}")
    return stats.equal_cost_threshold([{"class": "healthy", "score": r["p_yes"]} for r in fit])


def arm_scores(arm: str, inputs: list[dict]) -> tuple[dict[Key, float], dict]:
    """Score map and run facts for one arm."""
    if arm == "control":
        return {}, {}
    if arm == "word_check":
        hashes = {(r["doc_id"], r["page"]): r["liteparse_sha256"] for r in inputs}
        rows = read_json(EXP38 / "output" / "candidate_a.json")["rows"]
        scores = {
            (r["doc_id"], r["page"]): r["score"]
            for r in rows
            if r["tier"] == "liteparse" and r["text_sha256"] == hashes[(r["doc_id"], r["page"])]
        }
        return scores, {"reused_pages": len(scores)}
    path = OUTPUT / f"scores_{arm}.json"
    if not path.exists():
        return {}, {"missing": True}
    payload = read_json(path)
    rows = payload["rows"]
    tokens = [r["input_tokens"] for r in rows if r.get("input_tokens")]
    facts = {
        "scored_pages": len(rows),
        "failed_pages": len(payload["failures"]),
        "models": sorted({str(r["model"]) for r in rows}),
        "mean_seconds_per_page": sum(r["seconds"] for r in rows) / len(rows) if rows else None,
        "total_seconds": sum(r["seconds"] for r in rows),
        "input_tokens": sum(tokens),
    }
    if arm == "jev_image":
        facts["usd_spent_estimate"] = round(sum(tokens) * PRICE_PER_INPUT_TOKEN, 4)
    return {(r["doc_id"], r["page"]): r["p_yes"] for r in rows}, facts


def summarise(current: dict) -> dict:
    """Compute page and document results for every arm."""
    inputs = read_json(OUTPUT / "inputs.json")["rows"]
    documents = read_json(EXP33 / "output" / "arm_sampled_baseline" / "routing.json")["rows"]
    labels = {d: v["label"] for d, v in read_json(EXP33 / "labels.json")["documents"].items()}
    classes = {(r["doc_id"], r["page"]): r["class"] for r in inputs}
    rescued = {d["doc_id"] for d in documents if d["extraction_fallback_backend"] == "liteparse"}
    all_scored = {(r["doc_id"], r["page"]) for r in inputs if r["scored"] and r["doc_id"] in rescued}
    classified = {k for k in all_scored if classes[k] in ("junk", "healthy")}
    thresholds = {
        "control": None,
        "word_check": current["arms"]["word_check"]["threshold"],
        "clef_image": current["thresholds"]["clef_image"]["value"],
        "jev_image": current["thresholds"]["jev_image"]["value"],
    }
    arms = {}
    for arm in ARMS:
        scores, facts = arm_scores(arm, inputs)
        flags = flagged(scores, thresholds[arm])
        result: dict[str, Any] = {"threshold": thresholds[arm], "facts": facts}
        result["pages"] = page_metrics(classes, flags, set(scores) if arm != "control" else set(classes))
        populations = {"classified": classified}
        if arm != "word_check":
            populations["primary"] = all_scored
        for name, keys in populations.items():
            for rule in ("ten_percent", "one_page"):
                routing = route(documents, labels, flags, keys, rule)
                result[f"{name}_{rule}"] = {"pass_rule": pass_rule(routing), "routing": routing}
        arms[arm] = result
    decides = "primary_ten_percent"
    local = arms["clef_image"].get(decides, {}).get("pass_rule", {}).get("pass")
    hosted_ready = not arms["jev_image"]["facts"].get("missing") and thresholds["jev_image"] is not None
    local_ready = not arms["clef_image"]["facts"].get("missing") and thresholds["clef_image"] is not None
    verdict = None
    if hosted_ready and local_ready:
        verdict = "PASS" if local else "FAIL"
    return {
        "experiment": "43-image-rescue-gate-2026-11-02",
        "decides": f"clef_image {decides}",
        "verdict": verdict,
        "verdict_note": None if verdict else "no verdict: an image arm has no scores or threshold",
        "hosted_pass": arms["jev_image"].get(decides, {}).get("pass_rule", {}).get("pass"),
        "population_sizes": {"rescued_scored_pages": len(all_scored), "rescued_classified": len(classified)},
        "arms": arms,
    }


def main() -> None:
    """Fit one threshold, or write output/summary.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", choices=("clef_image", "jev_image"))
    args = parser.parse_args()
    current = plan()
    if args.fit:
        rows = read_json(OUTPUT / f"scores_{args.fit}.json")["rows"]
        value = fit_threshold(rows)
        flagged_fit = sum(r["p_yes"] < value for r in rows if r["phase"] == "fit")
        print(f"{args.fit} threshold {value!r}: {flagged_fit}/{FIT_PAGES} fit pages flag", flush=True)
        return
    summary = summarise(current)
    atomic_json(OUTPUT / "summary.json", summary)
    print(f"verdict: {summary['verdict']} (hosted pass: {summary['hosted_pass']})", flush=True)


if __name__ == "__main__":
    main()
