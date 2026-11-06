"""Step 2: local reference transcriptions and page labels, frozen before any router score.

    uv run --no-sync python -u label_pages.py references --resume
    uv run --no-sync python label_pages.py labels

``references`` transcribes each page with a local OCR engine through the
shipped OCR routes (dots-mocr, one page per request, offline). Nothing leaves
the machine. The text goes to ``output/.private/references/``; the committed
``output/reference_state.json`` holds status, hashes and timings only.

``labels`` applies the Experiment 33 token rule (``build_labels.tokens`` and
``recall``, imported by path with a pinned SHA-256) to the shipped page text
against the reference, with the frozen class thresholds of Experiments 38 and
42: ``junk`` below 0.50, ``healthy`` at 0.80 or more, ``grey`` between. It
writes ``output/labels.json`` and, once, the operator review list
``output/label_review.json``. Both steps refuse to run once a router score
exists, so the labels cannot follow the scores.
"""

from __future__ import annotations

import argparse
import os
import random
import time
from collections import Counter
from typing import Any

from exp47_io import (
    CORPUS,
    INPUTS,
    LABEL_REVIEW,
    LABELS,
    OUTPUT,
    REFERENCE_STATE,
    atomic_json,
    frozen_file,
    git_clean,
    load_module,
    log,
    plan,
    private_path,
    read_json,
    score_files,
    sha256,
    text_sha256,
)

# exp47_io puts experiments/ on sys.path, so _lib imports after it.
from _lib.run_safety import exclusive_lock  # noqa: E402

TOKEN_RULE_ITEM = "Experiment 33 build_labels.py (token rule)"  # noqa: S105 - a plan item name
SET_CHECK = OUTPUT / "set_check.json"


def refuse_after_scores() -> None:
    """Labels are frozen before any router score: stop when a score file exists."""
    found = score_files()
    if found:
        raise SystemExit(f"router scores exist ({found[0].name}); labels are frozen: stop")


# ---------------------------------------------------------------- references


def ocr_routes(workers_dir: str) -> tuple[Any, Any]:
    """The shipped host OCR routes with dots-mocr as the only engine."""
    from omrs.capabilities import build_ocr_routes
    from omrs.config import Settings

    settings = Settings(
        ocr_fallback_enabled=True, ocr_workers_dir=workers_dir, ocr_engines=("dots-mocr",)
    )
    return settings, build_ocr_routes(settings)


def references(resume: bool) -> None:
    """Transcribe every page of inputs.json locally, one page per request."""
    refuse_after_scores()
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    from omrs.integrations.ocr_worker.client import OcrWorkerError
    from omrs.integrations.ocr_worker.routes import request_timeout

    inputs = read_json(INPUTS)
    manifest = read_json(OUTPUT.parent / "corpus_manifest.json")
    manifest_files = {d["id"]: d["file"] for d in manifest["documents"]}
    with exclusive_lock(private_path("locks", "references.lock")):
        if REFERENCE_STATE.exists() and not resume:
            raise SystemExit(f"{REFERENCE_STATE.name} exists; use --resume")
        state = read_json(REFERENCE_STATE) if REFERENCE_STATE.exists() else {"pages": {}}
        settings, routes = ocr_routes(os.environ.get("EXP47_OCR_WORKERS_DIR", ""))
        try:
            client = routes.select()
            if client is None:
                raise SystemExit(
                    "no OCR route: set EXP47_OCR_WORKERS_DIR to the ocr-workers folder"
                )
            fp = routes.fingerprint
            state["engine"] = {
                "backend_id": fp.backend_id,
                "model": fp.model_identity,
                "protocol_version": fp.protocol_version,
            }
            for doc_id, doc in inputs["documents"].items():
                for row in doc["rows"]:
                    key = f"{doc_id}:{row['page']}"
                    out = private_path("references", doc_id, f"p{row['page']:03d}.md")
                    if state["pages"].get(key, {}).get("status") == "ok" and out.is_file():
                        continue
                    start = time.perf_counter()
                    try:
                        result = client.parse(
                            str(CORPUS / manifest_files[doc_id]),
                            pages=[row["page"]],
                            timeout=request_timeout(settings, 1),
                        )
                        text = (result.pages_markdown or (result.markdown,))[0]
                        out.write_text(text, encoding="utf-8")
                        entry = {"status": "ok", "sha256": text_sha256(text), "chars": len(text)}
                    except OcrWorkerError as exc:
                        entry = {"status": "error", "code": exc.code}
                    entry["seconds"] = round(time.perf_counter() - start, 2)
                    state["pages"][key] = entry
                    atomic_json(REFERENCE_STATE, state)
                    log(f"[reference] {key} {entry['status']} {entry['seconds']} s")
        finally:
            routes.close()


# ---------------------------------------------------------------- labels


def classify(text: str, reference: str | None, rule: Any, thresholds: dict) -> dict:
    """Class of one page: the shipped page text against its local reference."""
    text_tokens = rule.tokens(text)
    if reference is None:
        return {
            "class": "excluded",
            "exclusion_reason": "reference failed",
            "recall": None,
            "reference_tokens": 0,
            "text_tokens": len(text_tokens),
        }
    ref_tokens = rule.tokens(reference)
    recall = rule.recall(text, ref_tokens)
    reason = None
    if len(ref_tokens) < thresholds["min_reference_tokens"]:
        reason = f"reference below {thresholds['min_reference_tokens']} tokens"
    elif not text_tokens:
        reason = "no text layer tokens"
    label = "excluded"
    if reason is None:
        if recall < thresholds["junk_below"]:
            label = "junk"
        elif recall >= thresholds["healthy_at"]:
            label = "healthy"
        else:
            label = "grey"
    return {
        "class": label,
        "exclusion_reason": reason,
        "recall": recall,
        "reference_tokens": len(ref_tokens),
        "text_tokens": len(text_tokens),
    }


def review_sample(rows: list[dict], healthy_count: int, seed: int) -> list[dict]:
    """Every junk and grey page, plus a seeded sample of healthy pages, for the operator."""
    pick = [r for r in rows if r["class"] in ("junk", "grey")]
    healthy = [r for r in rows if r["class"] == "healthy"]
    pick += random.Random(seed).sample(healthy, min(healthy_count, len(healthy)))  # noqa: S311
    return [
        {"doc_id": r["doc_id"], "page": r["page"], "class": r["class"], "verdict": None}
        for r in sorted(pick, key=lambda r: (r["doc_id"], r["page"]))
    ]


def set_check(rows: list[dict], minimum: dict) -> dict:
    """The sample-size preconditions on pages the scan did not flag (plan ``set_check``)."""
    unflagged = [r for r in rows if not r["needs_ocr"]]
    junk = [r for r in unflagged if r["class"] == "junk"]
    healthy = [r for r in unflagged if r["class"] == "healthy"]
    found = {
        "unflagged_junk_pages": len(junk),
        "unflagged_junk_documents": len({r["doc_id"] for r in junk}),
        "unflagged_healthy_pages": len(healthy),
        "unflagged_healthy_documents": len({r["doc_id"] for r in healthy}),
    }
    return {
        "found": found,
        "minimum": minimum,
        "pass": all(found[k] >= v for k, v in minimum.items()),
    }


def labels(current: dict) -> dict:
    """Label every page and write labels.json, the review list and the set check."""
    refuse_after_scores()
    rule = load_module(frozen_file(current, TOKEN_RULE_ITEM), "exp33_build_labels")
    spec = current["labels"]
    inputs = read_json(INPUTS)
    state = read_json(REFERENCE_STATE)
    rows = []
    for doc_id, doc in inputs["documents"].items():
        texts = read_json(private_path("text", f"{doc_id}.json"))
        for row in doc["rows"]:
            text = texts[str(row["page"])]
            if text_sha256(text) != row["markdown_sha256"]:
                raise SystemExit(f"{doc_id} p{row['page']}: page text differs from inputs.json")
            ref = state["pages"].get(f"{doc_id}:{row['page']}", {})
            reference = None
            if ref.get("status") == "ok":
                reference = private_path("references", doc_id, f"p{row['page']:03d}.md").read_text(
                    encoding="utf-8"
                )
                if text_sha256(reference) != ref["sha256"]:
                    raise SystemExit(f"{doc_id} p{row['page']}: reference differs from its state")
            rows.append(
                {
                    **{
                        k: row[k]
                        for k in ("doc_id", "page", "group", "needs_ocr", "markdown_sha256")
                    },
                    **classify(text, reference, rule, spec["thresholds"]),
                }
            )
    counts = Counter((r["doc_id"], r["class"]) for r in rows)
    documents = {
        d: {c: counts[(d, c)] for c in ("junk", "healthy", "grey", "excluded")}
        for d in inputs["documents"]
    }
    payload = {
        "inputs_sha256": sha256(INPUTS),
        "reference_state_sha256": sha256(REFERENCE_STATE),
        "thresholds": spec["thresholds"],
        "rows": rows,
        "documents": documents,
    }
    atomic_json(LABELS, payload)
    if not LABEL_REVIEW.exists():
        review = review_sample(rows, spec["review"]["healthy_sample"], current["seed"])
        atomic_json(LABEL_REVIEW, {"reviewer": None, "date": None, "pages": review})
    check = set_check(rows, current["set_check"]["minimum"])
    atomic_json(SET_CHECK, check)
    log(f"[labels] {Counter(r['class'] for r in rows)}; set check pass: {check['pass']}")
    return payload


def labels_frozen(current: dict, clean: Any = git_clean) -> list[str]:
    """Reasons the labels are not frozen yet; scoring needs an empty list."""
    reasons = []
    for path in (LABELS, LABEL_REVIEW, SET_CHECK):
        if not path.exists() or not clean(path):
            reasons.append(f"{path.name} is missing or not committed")
    if reasons:
        return reasons
    review = read_json(LABEL_REVIEW)
    pages = review["pages"]
    if (
        not review.get("reviewer")
        or not review.get("date")
        or any(p["verdict"] is None for p in pages)
    ):
        reasons.append("the operator label review is not complete")
    disagree = sum(p["verdict"] == "disagree" for p in pages)
    if disagree > current["labels"]["review"]["max_disagreements"]:
        reasons.append(f"{disagree} label disagreements: fix by amendment before scoring")
    if not read_json(SET_CHECK)["pass"]:
        reasons.append("the set check failed: the run is INCONCLUSIVE before scoring")
    if read_json(LABELS)["inputs_sha256"] != sha256(INPUTS):
        reasons.append("labels.json was made from another inputs.json")
    return reasons


def main() -> None:
    """Run one labelling step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("references", "labels"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    current = plan()
    if args.step == "references":
        references(args.resume)
    else:
        labels(current)


if __name__ == "__main__":
    main()
