"""Human labels for two labellers and the faithfulness gate (tasks 15.8 and 16.18).

Usage (reads saved files only, runs on the Mac; one restricted label folder)::

    labels35.py sample --out-dir OUT --label-dir LABELS
    labels35.py l2 --label-dir LABELS --plan full|staged|faith-full
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
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import claimkinds35
import correct35
import differential35
import kindgate35
import labelpage35
from bootstrap35 import BootResult, bootstrap_by_question
from experiments._lib.stats_d6 import cohen_kappa
from faithpool35 import (  # noqa: F401 - re-exported names
    PER_CELL,
    SEED_FAITH,
    KindsMissing,
    chunk_size,
    draw_faithfulness,
    faithfulness_claims,
    require_kinds,
)
from outputs35 import Layout, NoRunFiles, read_rows, write_json

CORE = correct35.CORE
CHECKERS = ("chat", "clef_flash")
SEED_L2 = {"claim_kinds": 20261122, "faithfulness": 20261123}
SEED_GATE_KAPPA = 20261125
SEED_DIFFERENCE = 20261126
SEED_L1_L2 = 20261129
#: Staged plan: L2's first-stage size per set (pre-registration section 11.3).
L2_FIRST = {"claim_kinds": 30, "faithfulness": 135}
L2_PER_CELL = 15
# A18 (2026-11-27): L2 labels every faithfulness claim; claim kinds stay staged.
FULL_SETS = {"full": set(L2_FIRST), "staged": set(), "faith-full": {"faithfulness"}}
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


def label_counts(sizes: Mapping[str, int], plan: str) -> dict[str, int]:
    """Return the labels L1 and L2 give (L2 in the staged plan: first stage only)."""
    l1 = sum(sizes.values())
    full = FULL_SETS[plan]
    l2 = sum(n if s in full else L2_FIRST.get(s, n) for s, n in sizes.items())
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
        if set_name in FULL_SETS[plan] or set_name not in L2_FIRST:
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


def _agreement_stats(pairs: Sequence[tuple[str, str]]) -> dict[str, float | None]:
    """Prevalence of "supported" in the human labels, raw agreement and PABAK (R10)."""
    if not pairs:
        return {"prevalence": None, "raw_agreement": None, "pabak": None}
    agreement = sum(a == b for a, b in pairs) / len(pairs)
    return {
        "prevalence": sum(a == "supported" for a, _ in pairs) / len(pairs),
        "raw_agreement": agreement,
        "pabak": 2 * agreement - 1,
    }


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

    def pairs(group: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
        return [(_binary(reference[i["item_id"]]), verdicts[i["item_id"]]) for i in group]

    def boot(group: Sequence[Mapping[str, Any]]):
        rows = list(zip(map(_unit, group), pairs(group), strict=True))
        return bootstrap_by_question(rows, _kappa, n=n, seed=SEED_GATE_KAPPA, fill=0.0)

    kappa = boot(judged)
    known = [i for i in judged if reference[i["item_id"]] != labelpage35.CANT_TELL]
    return {
        "pass": checker_passes(kappa),
        "kappa": kappa.as_dict(),
        **_agreement_stats(pairs(judged)),
        "kappa_cant_tell_left_out": boot(known).as_dict(),
        "cant_tell_left_out_stats": _agreement_stats(pairs(known)),
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
        specificity[c] = {str(lv): _none(differential35.specificity(rows, lv)) for lv in levels}
        sensitivity[c] = {str(lv): _none(differential35.sensitivity(rows, lv)) for lv in levels}
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
    boot = differential35.paired_bootstrap(
        glm,
        {
            "specificity": differential35.specificity_difference,
            "sensitivity": differential35.sensitivity_difference,
        },
        n=n,
        seed=SEED_DIFFERENCE,
    )
    diff, sens_diff = boot["specificity"], boot["sensitivity"]
    spec_zero = differential35.excludes_zero(diff)
    sens_zero = differential35.excludes_zero(sens_diff)
    untestable = not diff.testable or not sens_diff.testable
    rows_out = (
        FAITH_ROWS if (not checkers["chat"]["pass"] or untestable or spec_zero or sens_zero) else []
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
            "sensitivity_difference": sens_diff.as_dict(),
            "specificity_excludes_zero": spec_zero,
            "sensitivity_excludes_zero": sens_zero,
            "excludes_zero": spec_zero or sens_zero,
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


def write_page(
    label_dir: Path,
    set_name: str,
    *,
    only: Sequence[str] | None = None,
    model_labeller: bool = False,
) -> Path:
    """Write one set's blind page; with *only*, the page holds just those items (L2 subset).

    With *model_labeller*, write the model-labeller copy (own draft storage, A18 item 32).
    """
    items = read_sample(label_dir, set_name)
    if only is not None:
        keep = set(only)
        items = [i for i in items if i["item_id"] in keep]
    suffix = ("-L2-subset" if only is not None else "") + ("-model" if model_labeller else "")
    path = label_dir / f"label-{set_name}{suffix}.html"
    labelpage35.write_page(path, set_name, items, model_labeller=model_labeller)
    return path


def saved_verdicts(out_dir: Path, items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Read each checker's saved verdict for every sample claim from its run folder."""
    out: dict[str, dict[str, str]] = {c: {} for c in CHECKERS}
    layout = Layout(out_dir)
    for item in items:
        folder = layout.run_dir(item["dataset"], "answer", item["setup"], item["run"])
        if not (folder / "answer.jsonl").exists():
            raise NoRunFiles(f"{folder} holds no answer.jsonl for sample item {item['item_id']}")
        answer = {r["qid"]: r for r in read_rows(folder / "answer.jsonl")}[item["qid"]]
        for c in CHECKERS:
            judge = {r["qid"]: r for r in read_rows(folder / f"judge-{c}.jsonl")}.get(item["qid"])
            if judge is not None and not judge.get("missing"):
                pairs = claimkinds35.align(
                    answer,
                    judge,
                    where=f"{item['dataset']}/{item['setup']}/run{item['run']}/{item['qid']}",
                )
                verdict = pairs[item["index"]][1].get("verdict")
                # Section 12: an unparseable verdict is returned content, so not supported.
                out[c][item["item_id"]] = "unsupported" if verdict == "unparseable" else verdict
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
        if name == "sample":
            p.add_argument("--gate", type=Path, help="classifier gate 3 gate.json")
        if name == "l2":
            p.add_argument("--plan", choices=tuple(FULL_SETS), required=True)
        if name == "page":
            p.add_argument("--set", choices=tuple(SAMPLE_FILES), required=True)
            p.add_argument("--l2-subset", action="store_true")
            p.add_argument("--model-labeller", action="store_true")
        if name == "faithgate":
            p.add_argument("--n", type=int, default=10_000)
    args = parser.parse_args(argv)
    d = args.label_dir
    if args.command == "sample":
        version = kindgate35.gate_version(args.gate)  # None: registered fallback, no kinds
        require_kinds(args.out_dir, version)
        claims = faithfulness_claims(args.out_dir, correct35._questions(CORE), version)
        write_sample(d, draw_faithfulness(claims))
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
        print(write_page(d, args.set, only=only, model_labeller=args.model_labeller), flush=True)
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
