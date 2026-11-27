"""Blind relevance audit for H3 of Experiment 35 (A18; pre-registration sections 11.3 and 21).

The audit measures how far unjudged units bias the hybrid-on against hybrid-off
contrast (row 4). It always runs, on every core dataset, and decides nothing.

Subcommands (all take ``--out``, the joined run output folder; files go in
``<out>/audit`` unless ``--audit-dir`` says otherwise):

- ``frame``: per core dataset, the (question, unit) pairs at ranks 1 to 3 in any
  hybrid-on setup and in no hybrid-off setup (arm ``hon_only``), and the reverse
  (arm ``hoff_only``), with no qrels judgement for the question. Reads the score
  records of both halves (``ranked_units``); the 72 setups only (no ``-t20k``).
  A placeholder unit (an unmapped chunk) has no text to label and is left out.
  Writes ``frame.json``.
- ``sample``: draws 50 pairs per arm per core dataset and writes
  ``audit-sample.json`` (with arm, for the analysis) and
  ``audit-items-blind.json`` (no arm, setup, score or rank, for the label page).
  Draw order, one ``random.Random(20261120)``: datasets sorted, then arm
  ``hoff_only``, then ``hon_only``; each arm's frame sorted by (question ID,
  unit ID) and sampled with ``sample``; then all items shuffled with the same
  generator. A frame under 50 gives all of it; both counts are recorded.
- ``report``: reads the L1 and L2 label files and the optional resolutions
  (``labels-relevance_audit-L1.json``, ``-L2.json``,
  ``resolved-relevance_audit.json``) and writes ``audit-report.json``: share
  relevant per dataset and arm with a 95% Wilson interval, the difference between
  arms (hybrid on minus off) with a 95% percentile bootstrap by question (10,000
  resamples, seed 20261145), "can't tell" both ways, and the estimated H3 bias.
  Descriptive only: no decision, row or Holm family changes.

The reference label follows ``labelpage35.reference_labels``: the agreed label,
else the label agreed after discussion, else "can't tell".

Unit text is read as the oracle stage reads it (``oracle35.unit_text``): the search stage
saves no chunk text (section 14.2). ``sample`` needs ``--passages-dir``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import cells35  # noqa: E402
import datasets35  # noqa: E402
import factorial35  # noqa: E402
import labelpage35  # noqa: E402
import labels35  # noqa: E402
import oracle35  # noqa: E402
import scoring35  # noqa: E402
import select35  # noqa: E402
from bootstrap35 import bootstrap_by_question  # noqa: E402
from experiments._lib.stats_d6 import wilson  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

SEED_SAMPLE, SEED_BOOTSTRAP, PER_ARM, TOP = 20261120, 20261145, 50, 3
#: Draw order of the arms inside each dataset.
ARMS = ("hoff_only", "hon_only")
SET_NAME = "relevance_audit"
RELEVANT, NOT_RELEVANT, CANT_TELL = "relevant", "not_relevant", labelpage35.CANT_TELL
CHOICES = (RELEVANT, NOT_RELEVANT, CANT_TELL)
#: The two readings of "can't tell": counted as not relevant, or as relevant.
WAYS = {"cant_tell_as_not_relevant": 0.0, "cant_tell_as_relevant": 1.0}
Pair = tuple[str, str]
Frame = dict[str, dict[str, list[Pair]]]


def _arm_of(setup: str) -> str | None:
    parsed = select35.parse_setup(setup)
    if parsed.t20k:
        return None
    return "hon_only" if parsed.hybrid == "on" else "hoff_only"


def frame(
    records: Iterable[Mapping[str, Any]], qrels: Mapping[str, Mapping[str, Mapping[str, int]]]
) -> Frame:
    """Return per core dataset and arm the sorted (question, unit) frame pairs.

    Args:
        records: Search score records (``dataset``, ``setup``, ``qid``, ``ranked_units``).
        qrels: Per dataset, per question, the judged units.

    Returns:
        ``{dataset: {"hon_only": [...], "hoff_only": [...]}}``; a pair appears once.
    """
    seen: dict[str, dict[str, set[Pair]]] = {}
    for row in records:
        arm = _arm_of(row["setup"])
        if arm is None or row["dataset"] not in qrels:
            continue
        judged = qrels[row["dataset"]].get(str(row["qid"]), {})
        for unit in row["ranked_units"][:TOP]:
            if unit in judged or unit.startswith(scoring35.PLACEHOLDER):
                continue
            seen.setdefault(row["dataset"], {}).setdefault(arm, set()).add((str(row["qid"]), unit))
    out: Frame = {}
    for dataset in sorted(qrels):
        per = seen.get(dataset, {})
        on, off = per.get("hon_only", set()), per.get("hoff_only", set())
        out[dataset] = {"hon_only": sorted(on - off), "hoff_only": sorted(off - on)}
    return out


def _item_id(dataset: str, qid: str, unit: str) -> str:
    return f"{dataset}|{qid}|{unit}"


def draw(
    frames: Mapping[str, Mapping[str, Sequence[Pair]]],
) -> tuple[list[dict[str, str]], dict[str, dict[str, dict[str, int]]]]:
    """Draw the audit items, in the order the module docstring fixes.

    Returns:
        The shuffled items (``dataset``, ``qid``, ``unit``, ``arm``), and per
        dataset and arm the frame size and the number drawn.
    """
    rng = random.Random(SEED_SAMPLE)  # noqa: S311 - registered seed, not security
    items: list[dict[str, str]] = []
    counts: dict[str, dict[str, dict[str, int]]] = {}
    for dataset in sorted(frames):
        for arm in ARMS:
            pairs = sorted(frames[dataset].get(arm, ()))
            taken = rng.sample(pairs, min(PER_ARM, len(pairs)))
            counts.setdefault(dataset, {})[arm] = {"frame": len(pairs), "drawn": len(taken)}
            items += [{"dataset": dataset, "qid": q, "unit": u, "arm": arm} for q, u in taken]
    rng.shuffle(items)
    return items, counts


def build_items(
    drawn: Sequence[Mapping[str, str]],
    texts: Mapping[tuple[str, str, str], str],
    questions: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Add item ID, question text, reference answer and unit text to each drawn item."""
    out = []
    for item in drawn:
        q = questions[item["dataset"]][item["qid"]]
        out.append(
            {
                "item_id": _item_id(item["dataset"], item["qid"], item["unit"]),
                **item,
                "question": q.text,
                "reference": q.reference,
                "unit_text": texts[(item["dataset"], item["qid"], item["unit"])],
            }
        )
    return out


def blind_items(items: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Return the label-page items: no arm, setup, score or rank."""
    return [
        {
            "item_id": i["item_id"],
            "dataset": i["dataset"],
            "question": i["question"],
            "reference": i["reference"],
            "passage": i["unit_text"],
        }
        for i in items
    ]


def reference(
    l1: Mapping[str, str], l2: Mapping[str, str], resolved: Mapping[str, str]
) -> tuple[dict[str, str], int]:
    """Return the reference labels and the unresolved count (``labelpage35.reference_labels``)."""
    return labelpage35.reference_labels(l1, l2, resolved)


def read_labels(path: Path, labeller: str, item_ids: Sequence[str]) -> dict[str, str]:
    """Read one audit label file; refuse a wrong set or labeller, a bad choice or a gap."""
    found = json.loads(path.read_text(encoding="utf-8"))
    labels: dict[str, str] = dict(found.get("labels") or {})
    wanted = set(item_ids)
    bad = sorted(i for i, v in labels.items() if v not in CHOICES)
    problems = [found.get("set") != SET_NAME, found.get("labeller") != labeller]
    if any(problems) or bad or set(labels) != wanted:
        raise labelpage35.LabelError(
            f"{path.name}: needs set {SET_NAME!r}, labeller {labeller}, every item once, "
            f"choices {CHOICES}; bad choices {bad}"
        )
    return labels


def _group(items: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[Mapping]]]:
    out: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for i in items:
        out.setdefault(i["dataset"], {}).setdefault(i["arm"], []).append(i)
    return out


def _share(count: float, n: int) -> dict[str, Any]:
    return {
        "share": count / n if n else None,
        "wilson": list(wilson(int(count), n)) if n else None,
    }


def shares(
    items: Sequence[Mapping[str, Any]], ref: Mapping[str, str]
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return per dataset and arm the share relevant, "can't tell" counted both ways."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for dataset, per in sorted(_group(items).items()):
        for arm, rows in sorted(per.items()):
            labels = [ref[i["item_id"]] for i in rows]
            rel, cant = labels.count(RELEVANT), labels.count(CANT_TELL)
            out.setdefault(dataset, {})[arm] = {
                "n": len(rows),
                "relevant": rel,
                "cant_tell": cant,
                "not_relevant": labels.count(NOT_RELEVANT),
                "cant_tell_as_not_relevant": _share(rel, len(rows)),
                "cant_tell_as_relevant": _share(rel + cant, len(rows)),
            }
    return out


def _value(label: str, cant_tell_value: float) -> float:
    return {RELEVANT: 1.0, NOT_RELEVANT: 0.0}.get(label, cant_tell_value)


def kappa(
    items: Sequence[Mapping[str, Any]],
    l1: Mapping[str, str],
    l2: Mapping[str, str],
    *,
    n: int = 10_000,
) -> dict[str, Any]:
    """Return kappa L1 against L2 on the raw labels with its bootstrap interval.

    Section 11.3: seed 20261129, method of section 11.2 (resample questions);
    ``labels35.kappa_l1_l2`` does the work, so the audit follows the other sets.
    """
    return labels35.kappa_l1_l2(SET_NAME, items, l1, l2, n=n)


def difference(
    items: Sequence[Mapping[str, Any]], ref: Mapping[str, str], *, n: int = 10_000
) -> dict[str, dict[str, Any]]:
    """Return per dataset and reading the share difference hybrid on minus off.

    The interval is the 95% percentile bootstrap by question (seed 20261145,
    order-statistic rule of ``bootstrap35``); a resample without both arms is left out.
    """

    def stat(rows: list[tuple[str, float]]) -> float:
        on = [v for a, v in rows if a == "hon_only"]
        off = [v for a, v in rows if a == "hoff_only"]
        if not on or not off:
            return math.nan
        return math.fsum(on) / len(on) - math.fsum(off) / len(off)

    out: dict[str, dict[str, Any]] = {}
    for dataset, per in sorted(_group(items).items()):
        out[dataset] = {}
        for way, cant in WAYS.items():
            rows = [
                (i["qid"], (i["arm"], _value(ref[i["item_id"]], cant)))
                for arm in per
                for i in per[arm]
            ]
            out[dataset][way] = bootstrap_by_question(
                rows, stat, n=n, seed=SEED_BOOTSTRAP, fill=None
            ).as_dict()
    return out


def _adjusted(
    row: Mapping[str, Any],
    members: Mapping[str, set[Pair]],
    share: Mapping[str, float],
    gold: set[str],
) -> float:
    """Return nDCG@10 of one record with frame units at ranks 1 to 3 given the arm's share."""
    arm = _arm_of(row["setup"])
    pairs = members.get(arm or "", set())
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(gold), 10) + 1))
    extra = 0.0
    for rank, unit in enumerate(row["ranked_units"][:TOP], start=1):
        if (str(row["qid"]), unit) in pairs and unit not in gold:
            extra += share[arm or ""] / math.log2(rank + 1)
    return float(row["ndcg_at_10"]) + (extra / ideal if ideal else 0.0)


def _row4(records: Sequence[Mapping[str, Any]], dataset: str) -> float:
    cells = cells35.cell_means(records, factorial35.NDCG).get(dataset, {})
    d, _ = cells35.contrast(factorial35.ROWS[3], cells)
    return math.fsum(d.values()) / len(d) if d else math.nan


def bias(
    records: Iterable[Mapping[str, Any]],
    frames: Mapping[str, Mapping[str, Sequence[Pair]]],
    arm_shares: Mapping[str, Mapping[str, float]],
    gold: Mapping[str, Mapping[str, set[str]]],
) -> dict[str, dict[str, float]]:
    """Return per dataset the reported row 4, the adjusted row 4 and their difference.

    Row 4 is hybrid on minus off, marginal over the other factors (hypothesis H3).
    Per setup and question, each unjudged unit at ranks 1 to 3 that sits in the
    setup's arm frame counts with gain equal to that arm's audited share; units
    in both arms' top 3, ranks 4 to 10 and the ideal DCG stay as reported.
    """
    rows = [r for r in records if _arm_of(r["setup"]) is not None]
    out: dict[str, dict[str, float]] = {}
    for dataset, per in sorted(frames.items()):
        mine = [r for r in rows if r["dataset"] == dataset]
        members = {arm: set(map(tuple, pairs)) for arm, pairs in per.items()}
        share = arm_shares[dataset]
        adjusted = [
            {**r, factorial35.NDCG: _adjusted(r, members, share, gold[dataset][str(r["qid"])])}
            for r in mine
        ]
        reported, new = _row4(mine, dataset), _row4(adjusted, dataset)
        out[dataset] = {"reported_row4": reported, "adjusted_row4": new, "bias": new - reported}
    return out


def _bias_by_way(
    records: Sequence[Mapping[str, Any]],
    frames: Frame,
    stats: Mapping[str, Mapping[str, Mapping[str, Any]]],
    gold: Mapping[str, Mapping[str, set[str]]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for way in WAYS:
        usable = {
            d: {arm: per[arm][way]["share"] for arm in per}
            for d, per in stats.items()
            if all(per.get(a, {}).get(way, {}).get("share") is not None for a in ARMS)
        }
        out[way] = bias(records, {d: frames[d] for d in usable}, usable, gold)
    return out


# --- inputs from the run folder and the data folder ----------------------------------------


def load_scores(out: Path) -> list[dict[str, Any]]:
    """Return the search score records of both halves."""
    return [r for p in sorted((out / "scores").glob("[AB]/*/*.jsonl")) for r in read_rows(p)]


def load_qrels(names: Iterable[str]) -> dict[str, dict[str, dict[str, int]]]:
    """Return the qrels of each dataset in *names* (``datasets35.qrels``)."""
    root = datasets35.data_root()
    return {n: datasets35.qrels(n, root) for n in sorted(names)}


def load_questions(names: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Return per dataset the questions by ID (text and reference answer)."""
    root = datasets35.data_root()
    return {n: {q.qid: q for q in datasets35.load_questions(n, root)} for n in sorted(names)}


def load_gold(names: Iterable[str]) -> dict[str, dict[str, set[str]]]:
    """Return per dataset and question the gold units used by the scores."""
    root = datasets35.data_root()
    return {
        n: {
            q: set(g.units)
            for q, g in scoring35.gold_table(n, datasets35.load_questions(n, root)).items()
        }
        for n in sorted(names)
    }


def load_texts(
    needed: Iterable[tuple[str, str, str]],
    *,
    passages: Path | None,
    pages: Callable[[str, str], str | None] | None,
) -> dict[tuple[str, str, str], str]:
    """Return the text of each needed (dataset, question, unit), read as the oracle stage reads it.

    The search stage saves no chunk text (section 14.2), so the text comes from
    the prepared passage files (``oracle35.unit_text``) and, for FinanceBench,
    from the page reader.

    Raises:
        datasets35.DatasetError: A unit has no text.
    """
    stems: dict[str, str] | None = None
    out: dict[tuple[str, str, str], str] = {}
    for dataset, qid, unit in sorted(set(needed)):
        if dataset == "freshstack" and stems is None:
            stems = oracle35.freshstack_stems(passages)
        out[(dataset, qid, unit)] = oracle35.unit_text(
            dataset, unit, passages=passages, pages=pages, stems=stems
        )
    return out


def _pinned_reader() -> Any:
    """Return the settings the page reader needs: the PDF reader ``plan.json`` pins, no OCR."""
    pins = _read_json(EXP_DIR / "plan.json")["pins"]["settings"]
    return types.SimpleNamespace(pdf_reader=pins["pdf_reader"], ocr_fallback_enabled=False)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _cmd_frame(out: Path, audit: Path) -> None:
    names = list(select35.CORE)
    frames = frame(load_scores(out), load_qrels(names))
    counts = {d: {a: len(frames[d][a]) for a in ARMS} for d in frames}
    write_json(audit / "frame.json", {"counts": counts, "pairs": frames})
    print(f"[audit] frame {counts}", flush=True)


def _cmd_sample(audit: Path, passages: Path | None) -> None:
    saved = _read_json(audit / "frame.json")
    pairs = {
        d: {a: [tuple(p) for p in v] for a, v in per.items()} for d, per in saved["pairs"].items()
    }
    drawn, counts = draw(pairs)
    needed = [(i["dataset"], i["qid"], i["unit"]) for i in drawn]
    pages = None
    if any(d == "financebench" for d, _, _ in needed):
        pages = oracle35.pdf_pages(_pinned_reader(), datasets35.data_root())
    texts = load_texts(needed, passages=passages, pages=pages)
    items = build_items(drawn, texts, load_questions(pairs))
    write_json(
        audit / "audit-sample.json",
        {"seed": SEED_SAMPLE, "per_arm": PER_ARM, "counts": counts, "items": items},
    )
    write_json(audit / "audit-items-blind.json", blind_items(items))
    print(f"[audit] sample {len(items)} items {counts}", flush=True)


def _cmd_report(out: Path, audit: Path, n: int) -> None:
    sample = _read_json(audit / "audit-sample.json")
    items = sample["items"]
    ids = [i["item_id"] for i in items]
    l1 = read_labels(audit / f"labels-{SET_NAME}-L1.json", "L1", ids)
    l2 = read_labels(audit / f"labels-{SET_NAME}-L2.json", "L2", ids)
    resolved_path = audit / f"resolved-{SET_NAME}.json"
    resolved = _read_json(resolved_path) if resolved_path.exists() else {}
    ref, unresolved = reference(l1, l2, resolved)
    stats = shares(items, ref)
    saved = _read_json(audit / "frame.json")
    frames = {
        d: {a: [tuple(p) for p in v] for a, v in per.items()} for d, per in saved["pairs"].items()
    }
    write_json(
        audit / "audit-report.json",
        {
            "unresolved": unresolved,
            "counts": sample["counts"],
            "shares": stats,
            "kappa": kappa(items, l1, l2),
            "difference": difference(items, ref, n=n),
            "bias": _bias_by_way(load_scores(out), frames, stats, load_gold(frames)),
        },
    )
    print(f"[audit] report {audit / 'audit-report.json'}", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand: ``frame``, ``sample`` or ``report``; return 0."""
    parser = argparse.ArgumentParser(prog="audit35.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("frame", "sample", "report"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, required=True, help="the joined run output folder")
        p.add_argument("--audit-dir", type=Path, help="audit files (default <out>/audit)")
        if name == "sample":
            p.add_argument("--passages-dir", type=Path, help="prepared passages folder")
        if name == "report":
            p.add_argument("--n", type=int, default=10_000, help="bootstrap resamples")
    args = parser.parse_args(argv)
    scoring35.require_half_b(args.out)  # the audit reads half-B scores (section 14.2)
    audit = args.audit_dir or args.out / "audit"
    handlers: dict[str, Callable[[], None]] = {
        "frame": lambda: _cmd_frame(args.out, audit),
        "sample": lambda: _cmd_sample(audit, getattr(args, "passages_dir", None)),
        "report": lambda: _cmd_report(args.out, audit, getattr(args, "n", 10_000)),
    }
    handlers[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
