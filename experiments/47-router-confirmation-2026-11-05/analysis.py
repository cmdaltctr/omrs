"""Step 5: summarise every arm and give the verdict, or withhold it.

    uv run --no-sync python analysis.py   # writes output/summary.json

Populations come from the frozen labels on pages the scan did not flag. A page
that an earlier page rule claimed (for example a maths page sent to OCR) goes
to OCR without the router, so it leaves the router populations. The verdict
uses the treatment arm (``clef_router``) and the primary gates only. It is
withheld when any scored population is incomplete (issue #171, point 1).
"""

from __future__ import annotations

import operator

from exp47_io import LABELS, OUTPUT, atomic_json, log, plan, read_json

from _lib.run_safety import population_gaps  # noqa: E402  (exp47_io sets sys.path)

Key = tuple[str, int]
ARMS = ("control", "clef_router", "jev_router")
DECIDES = "clef_router"
OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq}


def rate(part: int, whole: int) -> float | None:
    """part / whole, or None for an empty population."""
    return part / whole if whole else None


def arm_rows(arm: str) -> tuple[dict[Key, dict], dict[str, dict], dict[Key, bool]]:
    """Scored rows, per-document records and failed pages of one arm."""
    if arm == "control":
        return {}, {}, {}
    path = OUTPUT / f"scores_{arm}.json"
    if not path.exists():
        return {}, {}, {}
    payload = read_json(path)
    rows = {(r["doc_id"], r["page"]): r for d in payload["documents"].values() for r in d["rows"]}
    failed = {(doc, page): True for doc, pages in payload["failures"].items() for page in pages}
    return rows, payload["documents"], failed


def populations(labels: list[dict], documents: dict[str, dict]) -> dict[str, set[Key]]:
    """Router populations: unflagged pages of each class, minus pages an earlier rule claimed."""
    claimed = {(d, p) for d, rec in documents.items() for p in rec.get("claimed", [])}
    out: dict[str, set[Key]] = {
        "unflagged_junk": set(),
        "unflagged_healthy": set(),
        "unflagged_grey": set(),
    }
    for row in labels:
        key = (row["doc_id"], row["page"])
        name = f"unflagged_{row['class']}"
        if not row["needs_ocr"] and key not in claimed and name in out:
            out[name].add(key)
    return out


def per_document(labels: list[dict], rejected: set[Key], cost: float) -> dict[str, dict]:
    """Pages each document sends to OCR through the router, and the document-share views.

    The shipped router works in page mode: only the rejected pages go to OCR. The
    10% share and the one-page rule are reported as views, as the spec asks.
    """
    out: dict[str, dict] = {}
    for row in labels:
        doc = out.setdefault(
            row["doc_id"], {"pages": 0, "rejected_pages": [], "healthy_rejected": 0}
        )
        doc["pages"] += 1
        if (row["doc_id"], row["page"]) in rejected:
            doc["rejected_pages"].append(row["page"])
            doc["healthy_rejected"] += row["class"] == "healthy"
    for doc in out.values():
        count = len(doc["rejected_pages"])
        doc.update(
            ocr_seconds=round(count * cost, 1),
            routes_at_one_page=count >= 1,
            routes_at_ten_percent=count / doc["pages"] >= 0.10,
        )
    return out


def arm_summary(arm: str, labels: list[dict], current: dict, documents_ref: dict) -> dict:
    """Page, document, cost and speed results of one arm."""
    rows, documents, failed = arm_rows(arm)
    pops = populations(labels, documents_ref)
    rejected = {k for k, r in rows.items() if r["rejected"]}
    scored = {name: keys & set(rows) for name, keys in pops.items()}
    junk, healthy = pops["unflagged_junk"], pops["unflagged_healthy"]
    caught, wrong = len(junk & rejected), len(healthy & rejected)
    junk_docs = sorted({k[0] for k in junk})
    missed_docs = [d for d in junk_docs if not any(k in rejected for k in junk if k[0] == d)]
    warmup = current["stop_rules"]["warmup_pages"]
    timed = [r["seconds"] for r in list(rows.values())[warmup:] if r["p_yes"] is not None]
    seconds = sum(timed) / len(timed) if timed else None
    exact = current["frozen_thresholds"].get(arm, {}).get("exact_value")
    shipped = current["arms"].get(arm, {}).get("threshold")
    band = [
        k
        for k, r in rows.items()
        if exact
        and r["p_yes"] is not None
        and min(exact, shipped) <= r["p_yes"] < max(exact, shipped)
    ]
    cost = current["ocr_cost"]["seconds_per_page"]
    metrics = {
        "router_junk_recall": rate(caught, len(junk)),
        "healthy_false_reject_rate": rate(wrong, len(healthy)),
        "junk_documents_missed": len(missed_docs),
        "seconds_per_page": seconds,
    }
    expected = {k: v for k, v in pops.items() if k != "unflagged_grey"}
    gaps = (
        []
        if arm == "control"
        else population_gaps(
            expected, scored, {n: {k for k in keys if k in failed} for n, keys in expected.items()}
        )
    )
    return {
        "metrics": metrics,
        "counts": {
            "junk_pages": len(junk),
            "junk_caught": caught,
            "healthy_pages": len(healthy),
            "healthy_rejected": wrong,
            "grey_pages": len(pops["unflagged_grey"]),
            "grey_rejected": len(pops["unflagged_grey"] & rejected),
            "scored_pages": len(rows),
        },
        "junk_documents": junk_docs,
        "junk_documents_missed": missed_docs,
        "false_reject_ocr_seconds": round(wrong * cost, 1),
        "documents": per_document(labels, rejected, cost),
        "pages_between_shipped_and_exact_threshold": sorted(band),
        "population_gaps": gaps,
    }


def gate_results(metrics: dict, gates: list[dict]) -> list[dict]:
    """Evaluate each gate; a gate on a missing metric does not pass."""
    out = []
    for gate in gates:
        value = metrics.get(gate["metric"])
        passed = value is not None and OPS[gate["op"]](value, gate["threshold"])
        out.append({**gate, "observed": value, "pass": passed})
    return out


def compare_arms(first: str, second: str, labels: list[dict]) -> dict:
    """Page-by-page agreement of two arms on the pages both scored (report only).

    The comparison never changes the verdict. A page counts when both arms gave
    a P(yes); ``differ`` lists each page where only one arm rejects it.
    """
    a, _, _ = arm_rows(first)
    b, _, _ = arm_rows(second)
    classes = {(r["doc_id"], r["page"]): r["class"] for r in labels}
    both = sorted(
        k for k in set(a) & set(b) if a[k]["p_yes"] is not None and b[k]["p_yes"] is not None
    )
    tally = {"both_reject": 0, "neither_reject": 0, "only_first_rejects": 0, "only_second_rejects": 0}
    differ = []
    for key in both:
        ra, rb = a[key]["rejected"], b[key]["rejected"]
        if ra and rb:
            tally["both_reject"] += 1
        elif not ra and not rb:
            tally["neither_reject"] += 1
        else:
            tally["only_first_rejects" if ra else "only_second_rejects"] += 1
            differ.append(
                {
                    "doc_id": key[0],
                    "page": key[1],
                    "class": classes.get(key),
                    f"{first}_p_yes": a[key]["p_yes"],
                    f"{second}_p_yes": b[key]["p_yes"],
                    "rejected_by": first if ra else second,
                }
            )
    agree = tally["both_reject"] + tally["neither_reject"]
    return {
        "arms": [first, second],
        "pages_both_scored": len(both),
        "agree": agree,
        **tally,
        "agreement_rate": rate(agree, len(both)),
        "differ": differ,
    }


def summarise(current: dict, labels: dict) -> dict:
    """Every arm, the gates of the treatment arm and the verdict."""
    _, documents_ref, _ = arm_rows(DECIDES)
    arms = {arm: arm_summary(arm, labels["rows"], current, documents_ref) for arm in ARMS}
    gates = gate_results(arms[DECIDES]["metrics"], current["gates"])
    gaps = arms[DECIDES]["population_gaps"]
    primary = [g for g in gates if g["role"] == "primary"]
    verdict = None if gaps else ("PASS" if all(g["pass"] for g in primary) else "FAIL")
    return {
        "experiment": current["experiment_id"],
        "decides": f"{DECIDES}, primary gates",
        "verdict": verdict,
        "verdict_note": "; ".join(gaps) if gaps else None,
        "gates": gates,
        "arms": arms,
        "comparison": compare_arms(DECIDES, "jev_router", labels["rows"]),
    }


def main() -> None:
    """Write output/summary.json and print the verdict."""
    current = plan()
    summary = summarise(current, read_json(LABELS))
    atomic_json(OUTPUT / "summary.json", summary)
    log(f"verdict: {summary['verdict']} {summary['verdict_note'] or ''}")


if __name__ == "__main__":
    main()
