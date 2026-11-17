"""Human labels for two labellers and the faithfulness gate (tasks 15.8 and 16.18).

Usage (reads saved files only, runs on the Mac; one restricted label folder)::

    labels35.py sample --out-dir OUT --label-dir LABELS
    labels35.py l2 --label-dir LABELS --plan full|staged
    labels35.py page --label-dir LABELS --set faithfulness [--l2-subset]
    labels35.py agreement --label-dir LABELS
    labels35.py faithgate --out-dir OUT --label-dir LABELS

The three sets (pre-registration section 11.3) and their sample files in the
label folder: claim kinds, ``sample.json`` (``refusals35.py``, seed
20261112); faithfulness, ``faithfulness-sample.json`` (this module, seed
20261116); correctness, ``correctness-sample.json`` (``correct35.py``, seed
20261113). The gate files ``faithfulness-gate.json`` and
``correctness-gate.json`` record the time they were decided. The analysis
calls :func:`require_gates` before any H8a or H8b row.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import claimkinds35
import correct35
import labelpage35
from bootstrap35 import BootResult, bootstrap_by_question
from experiments._lib.stats_d6 import cohen_kappa
from outputs35 import read_rows, write_json

from omrs.core.answer.verify import split_claims

CORE = correct35.CORE
CHECKERS = ("chat", "clef_flash")
SEED_FAITH = 20261116
SEED_L2 = {"claim_kinds": 20261122, "faithfulness": 20261123}
SEED_GATE_KAPPA = 20261125
SEED_DIFFERENCE = 20261126
SEED_L1_L2 = 20261129
PER_CELL = 50
#: Staged plan: L2's first-stage size per set (pre-registration section 11.3).
L2_FIRST = {"claim_kinds": 30, "faithfulness": 135}
L2_PER_CELL = 15
ESCALATE_BELOW = 0.70
#: Rows a failed GLM-5.3 gate or the differential-error rule makes not testable.
FAITH_ROWS = [12, 13, 16, 17]
SAMPLE_FILES = {
    "claim_kinds": "sample.json",
    "faithfulness": "faithfulness-sample.json",
    "correctness": "correctness-sample.json",
}


class GateMissing(RuntimeError):
    """A gate file the analysis needs does not exist yet."""


def chunk_size(setup: str) -> int:
    """Return the chunk size in a setup name (``e4b-c1024-r4b-hon`` gives 1024)."""
    found = re.search(r"(?:^|-)c(\d+)(?:-|$)", setup)
    if found is None:
        raise ValueError(f"no chunk size in setup name {setup!r}")
    return int(found.group(1))


def faithfulness_claims(
    out_dir: Path, questions: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> list[dict[str, Any]]:
    """Return the faithfulness gate pool: crossed setups, core datasets, all runs and questions.

    A claim whose saved kind (``claim-kinds.jsonl`` of its own run folder) is
    ``refusal`` is left out. A claim of kind factual or mixed stays, and so
    does a claim the classifier left unclassified (no saved row, or kind
    ``unreadable``): section 12 treats it as factual (section 11.2).
    """
    claims: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*/*/run*/answer.jsonl")):
        dataset, setup, run = path.parts[-4], path.parts[-3], int(path.parts[-2][3:])
        if dataset not in CORE or "t20k" in setup:
            continue
        refusals = {
            r["claim_key"]
            for r in read_rows(path.parent / "claim-kinds.jsonl")
            if r["kind"] == "refusal"
        }
        for row in read_rows(path):
            evidence = row.get("evidence") or []
            texts = {e["ordinal"]: e["text"] for e in evidence}
            for index, (claim, ordinals) in enumerate(
                split_claims(row.get("answer") or "", len(evidence))
            ):
                if claimkinds35.claim_key(row["qid"], claim) in refusals:
                    continue
                claims.append(
                    {
                        "item_id": correct35.item_id(
                            "faithfulness", dataset, setup, run, row["qid"], index
                        ),
                        "dataset": dataset,
                        "setup": setup,
                        "run": run,
                        "qid": row["qid"],
                        "index": index,
                        "chunk_size": chunk_size(setup),
                        "question": questions[dataset][row["qid"]]["question"],
                        "claim": claim,
                        "passages": [texts[o] for o in ordinals if o in texts],
                    }
                )
    return claims


def draw_faithfulness(
    claims: Sequence[Mapping[str, Any]], *, seed: int = SEED_FAITH, per_cell: int = PER_CELL
) -> list[dict[str, Any]]:
    """Draw ``per_cell`` claims per (chunk size, core dataset), at most one per answer, shuffled."""
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    cells: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for c in claims:
        cells[(c["chunk_size"], c["dataset"])].append(c)
    items: list[dict[str, Any]] = []
    for cell in sorted(cells):
        pool = sorted(cells[cell], key=lambda c: c["item_id"])
        rng.shuffle(pool)
        used: set[tuple[str, int, str]] = set()
        picked: list[dict[str, Any]] = []
        for c in pool:
            answer = (c["setup"], c["run"], c["qid"])
            if answer not in used and len(picked) < per_cell:
                used.add(answer)
                picked.append(dict(c))
        items += picked
    rng.shuffle(items)
    return items


def label_counts(sizes: Mapping[str, int], plan: str) -> dict[str, int]:
    """Return the labels L1 and L2 give (L2 in the staged plan: first stage only)."""
    l1 = sum(sizes.values())
    l2 = l1 if plan == "full" else sum(L2_FIRST.get(s, n) for s, n in sizes.items())
    return {"L1": l1, "L2": l2}


def l2_items(plan: str, samples: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[str]]:
    """Return the item IDs L2 labels first, per set, in sample order.

    The full plan gives every item. The staged plan gives 30 claim kinds (seed
    20261122), 135 faithfulness claims (15 per chunk size and core dataset,
    seed 20261123) and every correctness answer.
    """
    out: dict[str, list[str]] = {}
    for set_name, items in samples.items():
        ids = [i["item_id"] for i in items]
        if plan == "full" or set_name not in L2_FIRST:
            out[set_name] = ids
            continue
        rng = random.Random(SEED_L2[set_name])  # noqa: S311
        if set_name == "claim_kinds":
            chosen = set(rng.sample(sorted(ids), L2_FIRST[set_name]))
        else:
            cells: dict[tuple[int, str], list[str]] = defaultdict(list)
            for i in items:
                cells[(i["chunk_size"], i["dataset"])].append(i["item_id"])
            chosen = {
                x for cell in sorted(cells) for x in rng.sample(sorted(cells[cell]), L2_PER_CELL)
            }
        out[set_name] = [x for x in ids if x in chosen]
    return out


def _unit(item: Mapping[str, Any]) -> tuple[str, str]:
    return (item["dataset"], item["qid"])


def _kappa(pairs: list[tuple[str, str]]) -> float:
    return cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])


def _both(
    items: Sequence[Mapping[str, Any]], l1: Mapping[str, str], l2: Mapping[str, str]
) -> list[Mapping[str, Any]]:
    return [i for i in items if i["item_id"] in l2 and i["item_id"] in l1]


def escalate(
    set_name: str, items: Sequence[Mapping[str, Any]], l1: Mapping[str, str], l2: Mapping[str, str]
) -> bool:
    """Return True when L2 must label the rest of a staged set.

    The subset kappa (raw labels) below 0.70 overall, or for faithfulness
    within any chunk-size level, or undefined, escalates.
    """
    subset = _both(items, l1, l2)
    groups = [subset]
    if set_name == "faithfulness":
        groups += [
            [i for i in subset if i["chunk_size"] == c]
            for c in sorted({i["chunk_size"] for i in subset})
        ]
    for group in groups:
        k = _kappa([(l1[i["item_id"]], l2[i["item_id"]]) for i in group])
        if math.isnan(k) or k < ESCALATE_BELOW:
            return True
    return False


def kappa_l1_l2(
    set_name: str,
    items: Sequence[Mapping[str, Any]],
    l1: Mapping[str, str],
    l2: Mapping[str, str],
    *,
    n: int = 10_000,
) -> dict[str, Any]:
    """Return kappa L1 against L2 with bootstrap intervals (seed 20261129).

    Per set; per chunk size for faithfulness; per core dataset for correctness.
    """
    both = _both(items, l1, l2)

    def boot(group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        rows = [(_unit(i), (l1[i["item_id"]], l2[i["item_id"]])) for i in group]
        return bootstrap_by_question(rows, _kappa, n=n, seed=SEED_L1_L2, fill=0.0).as_dict()

    out: dict[str, Any] = {"items": len(both), "overall": boot(both)}
    if set_name == "faithfulness":
        out["by_chunk_size"] = {
            str(c): boot([i for i in both if i["chunk_size"] == c])
            for c in sorted({i["chunk_size"] for i in both})
        }
    if set_name == "correctness":
        out["by_dataset"] = {
            d: boot([i for i in both if i["dataset"] == d])
            for d in CORE
            if any(i["dataset"] == d for i in both)
        }
    return out


def _binary(label: str) -> str:
    return "supported" if label == "supported" else "unsupported"


def _specificity(rows: list[tuple[int, bool, bool]], level: int) -> float:
    """Share of human-supported claims at *level* the checker calls supported (NaN when none)."""
    calls = [checker for c, human, checker in rows if c == level and human]
    return sum(calls) / len(calls) if calls else math.nan


def _difference(rows: list[tuple[int, bool, bool]]) -> float:
    return _specificity(rows, 2048) - _specificity(rows, 512)


def checker_passes(kappa: BootResult) -> bool:
    """Return True when kappa reaches 0.60 with a lower bound of at least 0.40."""
    return kappa.testable and kappa.estimate >= 0.60 and kappa.lower >= 0.40


def _checker_gate(
    items: Sequence[Mapping[str, Any]],
    reference: Mapping[str, str],
    verdicts: Mapping[str, str],
    n: int,
) -> dict[str, Any]:
    judged = [i for i in items if verdicts.get(i["item_id"]) in ("supported", "unsupported")]

    def boot(group: Sequence[Mapping[str, Any]]):
        rows = [
            (_unit(i), (_binary(reference[i["item_id"]]), verdicts[i["item_id"]])) for i in group
        ]
        return bootstrap_by_question(rows, _kappa, n=n, seed=SEED_GATE_KAPPA, fill=0.0)

    kappa = boot(judged)
    return {
        "pass": checker_passes(kappa),
        "kappa": kappa.as_dict(),
        "kappa_cant_tell_left_out": boot(
            [i for i in judged if reference[i["item_id"]] != labelpage35.CANT_TELL]
        ).as_dict(),
        "by_dataset": {
            d: boot([i for i in judged if i["dataset"] == d]).as_dict()
            for d in CORE
            if any(i["dataset"] == d for i in judged)
        },
        "cant_tell": sum(reference[i["item_id"]] == labelpage35.CANT_TELL for i in items),
        "missing_verdicts": len(items) - len(judged),
    }


def faithfulness_gate(
    items: Sequence[Mapping[str, Any]],
    reference: Mapping[str, str],
    verdicts: Mapping[str, Mapping[str, str]],
    *,
    decided_at: str,
    n: int = 10_000,
) -> dict[str, Any]:
    """Return the faithfulness gate and the differential-error rule (pre-registration 11.2).

    Args:
        items: The faithfulness sample items.
        reference: The reference human label by item ID ("can't tell" counts
            as not supported).
        verdicts: Checker name to (item ID to ``supported`` or ``unsupported``).
        decided_at: The time the gate is decided (ISO 8601).
        n: Resamples per bootstrap (10,000).

    Returns:
        The ``faithfulness-gate.json`` record. ``not_testable_rows`` lists rows
        12, 13, 16 and 17 for every core dataset when the GLM-5.3 gate fails or
        the differential-error rule fires; a failed Clef-Flash gate only marks
        its results not validated.
    """
    checkers = {c: _checker_gate(items, reference, verdicts[c], n) for c in CHECKERS}
    checkers["clef_flash"]["validated"] = checkers["clef_flash"]["pass"]
    levels = sorted({i["chunk_size"] for i in items})
    specificity: dict[str, dict[str, float | None]] = {}
    sensitivity: dict[str, dict[str, float | None]] = {}
    for c in CHECKERS:
        rows = [
            (
                i["chunk_size"],
                reference[i["item_id"]] == "supported",
                verdicts[c].get(i["item_id"]) == "supported",
            )
            for i in items
            if verdicts[c].get(i["item_id"]) in ("supported", "unsupported")
        ]
        specificity[c] = {str(lv): _none(_specificity(rows, lv)) for lv in levels}
        flipped = [(lv, not human, not called) for lv, human, called in rows]
        sensitivity[c] = {str(lv): _none(_specificity(flipped, lv)) for lv in levels}
    glm = [
        (
            _unit(i),
            (
                i["chunk_size"],
                reference[i["item_id"]] == "supported",
                verdicts["chat"].get(i["item_id"]) == "supported",
            ),
        )
        for i in items
        if verdicts["chat"].get(i["item_id"]) in ("supported", "unsupported")
    ]
    diff = bootstrap_by_question(
        glm, lambda r: _difference(list(r)), n=n, seed=SEED_DIFFERENCE, fill=None
    )
    excludes_zero = diff.testable and (diff.lower > 0 or diff.upper < 0)
    rows_out = (
        FAITH_ROWS if (not checkers["chat"]["pass"] or not diff.testable or excludes_zero) else []
    )
    return {
        "decided_at": decided_at,
        "seeds": {"kappa": SEED_GATE_KAPPA, "difference": SEED_DIFFERENCE},
        "n": n,
        "checkers": checkers,
        "differential_error": {
            "specificity": specificity,
            "sensitivity": sensitivity,
            "difference": diff.as_dict(),
            "excludes_zero": excludes_zero,
        },
        "not_testable_rows": rows_out,
    }


def _none(value: float) -> float | None:
    return None if math.isnan(value) else value


def require_gates(label_dir: Path) -> dict[str, set[int]]:
    """Refuse until both gate files exist; return the not-testable rows per core dataset.

    Raises:
        GateMissing: ``faithfulness-gate.json`` or ``correctness-gate.json`` is missing.
    """
    for name in ("faithfulness-gate.json", "correctness-gate.json"):
        if not (label_dir / name).exists():
            raise GateMissing(
                f"{label_dir / name} does not exist: decide the gate before any H8a or H8b row"
            )
    faith = json.loads((label_dir / "faithfulness-gate.json").read_text(encoding="utf-8"))
    corr = json.loads((label_dir / "correctness-gate.json").read_text(encoding="utf-8"))
    return {
        d: set(faith["not_testable_rows"]) | set(corr["result"]["not_testable_rows"].get(d, []))
        for d in CORE
    }


def write_sample(label_dir: Path, items: Sequence[Mapping[str, Any]]) -> None:
    """Write ``faithfulness-sample.json``."""
    write_json(label_dir / SAMPLE_FILES["faithfulness"], list(items))


def read_sample(label_dir: Path, set_name: str) -> list[dict[str, Any]]:
    """Read one set's sample items from the label folder."""
    found = json.loads((label_dir / SAMPLE_FILES[set_name]).read_text(encoding="utf-8"))
    return found["items"] if isinstance(found, dict) else found


def write_page(label_dir: Path, set_name: str, *, only: Sequence[str] | None = None) -> Path:
    """Write one set's blind page; with *only*, the page holds just those items (L2 subset)."""
    items = read_sample(label_dir, set_name)
    if only is not None:
        keep = set(only)
        items = [i for i in items if i["item_id"] in keep]
    path = label_dir / f"label-{set_name}{'-L2-subset' if only is not None else ''}.html"
    labelpage35.write_page(path, set_name, items)
    return path


def saved_verdicts(out_dir: Path, items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Read each checker's saved verdict for every sample claim from its run folder."""
    out: dict[str, dict[str, str]] = {c: {} for c in CHECKERS}
    for item in items:
        folder = out_dir / item["dataset"] / item["setup"] / f"run{item['run']}"
        answer = {r["qid"]: r for r in read_rows(folder / "answer.jsonl")}[item["qid"]]
        for c in CHECKERS:
            judge = {r["qid"]: r for r in read_rows(folder / f"judge-{c}.jsonl")}.get(item["qid"])
            if judge is not None and not judge.get("missing"):
                pairs = claimkinds35.align(
                    answer,
                    judge,
                    where=f"{item['dataset']}/{item['setup']}/run{item['run']}/{item['qid']}",
                )
                out[c][item["item_id"]] = pairs[item["index"]][1].get("verdict")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand: ``sample``, ``l2``, ``page``, ``agreement`` or ``faithgate``."""
    parser = argparse.ArgumentParser(prog="labels35.py")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sample", "l2", "page", "agreement", "faithgate"):
        p = sub.add_parser(name)
        p.add_argument("--label-dir", type=Path, required=True)
        if name in ("sample", "faithgate"):
            p.add_argument("--out-dir", type=Path, required=True)
        if name == "l2":
            p.add_argument("--plan", choices=("full", "staged"), required=True)
        if name == "page":
            p.add_argument("--set", choices=tuple(SAMPLE_FILES), required=True)
            p.add_argument("--l2-subset", action="store_true")
        if name == "faithgate":
            p.add_argument("--n", type=int, default=10_000)
    args = parser.parse_args(argv)
    d = args.label_dir
    if args.command == "sample":
        write_sample(
            d, draw_faithfulness(faithfulness_claims(args.out_dir, correct35._questions(CORE)))
        )
    elif args.command == "l2":
        write_json(
            d / "l2-items.json", l2_items(args.plan, {s: read_sample(d, s) for s in SAMPLE_FILES})
        )
    elif args.command == "page":
        only = (
            json.loads((d / "l2-items.json").read_text(encoding="utf-8"))[args.set]
            if args.l2_subset
            else None
        )
        print(write_page(d, args.set, only=only), flush=True)
    elif args.command == "agreement":
        out: dict[str, Any] = {}
        for s in SAMPLE_FILES:
            items = read_sample(d, s)
            ids = [i["item_id"] for i in items]
            l2_ids = json.loads((d / "l2-items.json").read_text(encoding="utf-8"))[s]
            _, l1 = labelpage35.read_labels(d / f"labels-{s}-L1.json", s, ids)
            _, l2 = labelpage35.read_labels(d / f"labels-{s}-L2.json", s, l2_ids)
            out[s] = {**kappa_l1_l2(s, items, l1, l2), "escalate": escalate(s, items, l1, l2)}
        write_json(d / "agreement.json", out)
    else:
        items = read_sample(d, "faithfulness")
        reference, unresolved = labelpage35.set_reference(
            d, "faithfulness", [i["item_id"] for i in items]
        )
        decided = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        result = faithfulness_gate(
            items, reference, saved_verdicts(args.out_dir, items), decided_at=decided, n=args.n
        )
        write_json(d / "faithfulness-gate.json", {**result, "unresolved": unresolved})
    return 0


if __name__ == "__main__":
    sys.exit(main())
