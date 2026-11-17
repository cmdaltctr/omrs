"""Correctness gate per core dataset for Experiment 35 (task 14.6; pre-registration 11.2).

Usage (reads saved files only, runs on the Mac)::

    correct35.py sample --out-dir OUT --halves HALVES_JSON --label-dir LABELS
    correct35.py page --label-dir LABELS
    correct35.py agree --out-dir OUT --label-dir LABELS

``sample`` draws 50 half-B questions per answer dataset with seed 20261113
and, for each, the run-1 answer of one answer setup the same seed picks
uniformly. After drop step 1 (``OUT/drops.json``) no Legal answer is drawn.
The sample holds no Ragas score. ``agree`` reads the L1 and L2 label files
(``labels-correctness-L1.json``, ``-L2.json``, and ``resolved-correctness.json``
for discussed items), builds the reference label (section 11.3), cuts the
Ragas ``answer_correctness`` score at 0.5 and writes
``correctness-gate.json`` with the time it was decided.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import budget35
import labelpage35
from bootstrap35 import BootResult, bootstrap_by_question
from experiments._lib.stats_d6 import cohen_kappa
from outputs35 import read_rows, write_json

CORE = ("bioasq", "financebench", "freshstack")
SEED = 20261113
SEED_KAPPA = 20261127
SEED_AUC = 20261128
PER_DATASET = 50
CUT = 0.5
#: Rows a failed correctness gate makes not testable (pre-registration section 11.2).
GATED_ROWS = [14, 15, 18, 19]
TREATMENTS = {"cant_tell_correct": True, "cant_tell_not_correct": False}
SET = "correctness"


def item_id(*parts: object) -> str:
    """Return an opaque item ID (no setup name or chunk size can be read from it)."""
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:16]


def _half_b(halves_path: Path, dataset: str) -> list[str]:
    halves = json.loads(halves_path.read_text(encoding="utf-8"))["halves"][dataset]
    return sorted(q for q, h in halves.items() if h == "B")


def draw(
    out_dir: Path,
    halves_path: Path,
    questions: Mapping[str, Mapping[str, Mapping[str, str]]],
    *,
    seed: int = SEED,
    per_dataset: int = PER_DATASET,
) -> list[dict[str, Any]]:
    """Draw the correctness label sample.

    Args:
        out_dir: The joined output folder (``<dataset>/<setup>/run1/answer.jsonl``).
        halves_path: ``halves.json`` (``{"halves": {dataset: {qid: "A" | "B"}}}``).
        questions: Dataset to (question ID to ``question`` and ``reference``).
        seed: The sample seed (20261113).
        per_dataset: Questions per dataset (50).

    Returns:
        The items in draw order: dataset, question, setup, question text,
        reference and answer text.
    """
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    items: list[dict[str, Any]] = []
    for dataset in sorted(budget35.answer_datasets(budget35.read_drops(out_dir))):
        setups = sorted(
            p.parent.parent.name for p in (out_dir / dataset).glob("*/run1/answer.jsonl")
        )
        for qid in rng.sample(_half_b(halves_path, dataset), per_dataset):
            setup = rng.choice(setups)
            answers = {
                r["qid"]: r for r in read_rows(out_dir / dataset / setup / "run1" / "answer.jsonl")
            }
            q = questions[dataset][qid]
            items.append(
                {
                    "item_id": item_id(SET, dataset, setup, qid),
                    "dataset": dataset,
                    "qid": qid,
                    "setup": setup,
                    "question": q["question"],
                    "reference": q["reference"],
                    "answer": answers[qid].get("answer") or "",
                }
            )
    return items


def write_sample(label_dir: Path, items: Sequence[Mapping[str, Any]]) -> None:
    """Write ``correctness-sample.json``."""
    write_json(label_dir / "correctness-sample.json", list(items))


def read_sample(label_dir: Path) -> list[dict[str, Any]]:
    """Read ``correctness-sample.json``."""
    return json.loads((label_dir / "correctness-sample.json").read_text(encoding="utf-8"))


def write_page(label_dir: Path) -> Path:
    """Write the blind correctness labelling page; return its path."""
    path = label_dir / "label-correctness.html"
    labelpage35.write_page(path, SET, read_sample(label_dir))
    return path


def auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Return the area under the ROC curve (ties count half), or NaN with one class."""
    pos = [s for s, y in zip(scores, labels, strict=True) if y]
    neg = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not pos or not neg:
        return math.nan
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _kappa(pairs: list[tuple[int, int]]) -> float:
    return cohen_kappa([h for h, _ in pairs], [r for _, r in pairs])


def _auc(pairs: list[tuple[int, float]]) -> float:
    return auc([s for _, s in pairs], [h for h, _ in pairs])


def passes(kappas: Mapping[str, BootResult], aucs: Mapping[str, BootResult]) -> bool:
    """Return the gate decision for one core dataset.

    Both kappa computations need a point estimate of at least 0.60 and a lower
    bound of at least 0.40, and each AUC needs a lower bound above 0.5. A
    result that is not testable fails.
    """
    kappa_ok = all(k.testable and k.estimate >= 0.60 and k.lower >= 0.40 for k in kappas.values())
    auc_ok = all(a.testable and a.lower > 0.5 for a in aucs.values())
    return kappa_ok and auc_ok


def _dataset(rows: list[tuple[str, str, float]], n: int) -> dict[str, Any]:
    """Figures for one dataset from (question, reference label, Ragas score) rows."""
    out: dict[str, Any] = {}
    kappas: dict[str, BootResult] = {}
    aucs: dict[str, BootResult] = {}
    for name, cant_tell_correct in TREATMENTS.items():
        human = [
            int(lab == "correct" or (lab == labelpage35.CANT_TELL and cant_tell_correct))
            for _, lab, _ in rows
        ]
        ragas = [int(score >= CUT) for _, _, score in rows]
        qids = [q for q, _, _ in rows]
        agreement = (
            sum(h == r for h, r in zip(human, ragas, strict=True)) / len(rows) if rows else math.nan
        )
        kappas[name] = bootstrap_by_question(
            list(zip(qids, zip(human, ragas, strict=True), strict=True)),
            _kappa,
            n=n,
            seed=SEED_KAPPA,
            fill=0.0,
        )
        aucs[name] = bootstrap_by_question(
            list(zip(qids, zip(human, [s for _, _, s in rows], strict=True), strict=True)),
            _auc,
            n=n,
            seed=SEED_AUC,
            fill=0.5,
        )
        out[name] = {
            "n": len(rows),
            "prevalence": sum(human) / len(rows) if rows else math.nan,
            "raw_agreement": agreement,
            "pabak": 2 * agreement - 1,
            "kappa": kappas[name].as_dict(),
            "auc": aucs[name].as_dict(),
        }
    out["pass"] = passes(kappas, aucs)
    return out


def agree(
    items: Sequence[Mapping[str, Any]],
    labels: Mapping[str, str],
    scores: Mapping[str, float | None],
    *,
    n: int = 10_000,
) -> dict[str, Any]:
    """Return the correctness gate per dataset.

    Args:
        items: The sample items.
        labels: The reference human label by item ID.
        scores: The Ragas ``answer_correctness`` score by item ID (None when unjudged).
        n: Resamples per bootstrap (10,000).

    Returns:
        One entry per dataset (``pass`` is None outside the core datasets),
        and ``not_testable_rows`` for every core dataset whose gate failed.
    """
    result: dict[str, Any] = {}
    for dataset in sorted({i["dataset"] for i in items}):
        mine = [i for i in items if i["dataset"] == dataset]
        rows = [
            (i["qid"], labels[i["item_id"]], scores[i["item_id"]])
            for i in mine
            if scores[i["item_id"]] is not None
        ]
        entry = _dataset(rows, n)
        entry["unscored"] = len(mine) - len(rows)
        if dataset not in CORE:
            entry["pass"] = None
        result[dataset] = entry
    result["not_testable_rows"] = {
        d: GATED_ROWS for d in CORE if d in result and result[d]["pass"] is False
    }
    return result


def _scores(out_dir: Path, items: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    scores: dict[str, float | None] = {}
    for item in items:
        rows = {
            r["qid"]: r
            for r in read_rows(out_dir / item["dataset"] / item["setup"] / "run1" / "ragas.jsonl")
        }
        metric = rows.get(item["qid"], {}).get("metrics", {}).get("ragas_answer_correctness") or {}
        scores[item["item_id"]] = metric.get("score")
    return scores


def _questions(datasets: Sequence[str]) -> dict[str, dict[str, dict[str, str]]]:
    import datasets35

    root = datasets35.data_root()
    return {
        d: {
            q.qid: {"question": q.text, "reference": q.reference}
            for q in datasets35.load_questions(d, root)
        }
        for d in datasets
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand: ``sample``, ``page`` or ``agree``."""
    parser = argparse.ArgumentParser(prog="correct35.py")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--halves", type=Path, required=True)
    s.add_argument("--label-dir", type=Path, required=True)
    p = sub.add_parser("page")
    p.add_argument("--label-dir", type=Path, required=True)
    a = sub.add_parser("agree")
    a.add_argument("--out-dir", type=Path, required=True)
    a.add_argument("--label-dir", type=Path, required=True)
    a.add_argument("--n", type=int, default=10_000)
    args = parser.parse_args(argv)
    if args.command == "sample":
        datasets = sorted(budget35.answer_datasets(budget35.read_drops(args.out_dir)))
        write_sample(args.label_dir, draw(args.out_dir, args.halves, _questions(datasets)))
    elif args.command == "page":
        print(write_page(args.label_dir), flush=True)
    else:
        items = read_sample(args.label_dir)
        labels, unresolved = labelpage35.set_reference(
            args.label_dir, SET, [i["item_id"] for i in items]
        )
        result = agree(items, labels, _scores(args.out_dir, items), n=args.n)
        decided = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        write_json(
            args.label_dir / "correctness-gate.json",
            {
                "decided_at": decided,
                "unresolved": unresolved,
                "seeds": {"kappa": SEED_KAPPA, "auc": SEED_AUC},
                "n": args.n,
                "result": result,
            },
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
