"""Claim-kind recheck of the freeze check (owner decision, 2026-11-26).

The fixed classifier prompt (gpt-oss-120b claim sorter, three rules and four new
examples) runs again on the gate-2 sample, without the four claims that are now
prompt examples (about 96 calls, under $0.10). The figures compare it with the
owner's gate-2 labels, with the definitions of ``refusals35.gate``. The result is
informational: this sample informed the fix, so a pass is optimistic. Gate 3 still
runs on fresh labels after the freeze.

Usage::

    kinds_recheck35.py prepare --gate2 DIR --examples classify-examples.json --out FILE
    kinds_recheck35.py split --input FILE --out-dir DIR     # pod: writes sample.json
    kinds_recheck35.py score --input FILE --out-dir DIR     # pod: writes recheck-summary.json

``prepare`` runs on the Mac and makes the one ``--extra-input`` file of the watcher.
``refusals35.py classify`` runs between ``split`` and ``score``. ``score`` exits 1 only
when a sample claim has no saved kind (a missing or failed call), never on the figures.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [p for p in (str(HERE.parent), str(HERE.parents[2])) if p not in sys.path]
import claimkinds35  # noqa: E402
import labelpage35  # noqa: E402
import refusals35  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

NOTE = (
    "Informational. The gate-2 sample informed the prompt fix, so a pass is optimistic. "
    "Gate 3 runs on fresh labels after the freeze."
)


def prepare(gate2: Path, examples_file: Path) -> dict[str, Any]:
    """Return the recheck input: the gate-2 sample without the prompt examples, and labels."""
    sample = json.loads((gate2 / "sample.json").read_text(encoding="utf-8"))
    examples = json.loads(examples_file.read_text(encoding="utf-8"))
    taken = {claimkinds35.claim_key(e["qid"], e["claim"]) for e in examples}
    ids = [i["item_id"] for i in sample["items"]]
    _, l1 = labelpage35.read_labels(gate2 / "claim_kinds-L1.json", "claim_kinds", ids)
    labels, _ = labelpage35.reference_labels(l1, {}, {})
    kept = [i for i in sample["items"] if i["claim_key"] not in taken]
    excluded = [i["claim_key"] for i in sample["items"] if i["claim_key"] in taken]
    return {
        "sample": {"seed": sample["seed"], "strata": sample["strata"], "items": kept},
        "labels": {i["item_id"]: labels[i["item_id"]] for i in kept},
        "excluded": excluded,
    }


def _defined(value: float) -> float | None:
    return None if math.isnan(value) else value


def per_kind(
    sample: Mapping[str, Any], labels: Mapping[str, str], kinds: Mapping[str, str]
) -> dict:
    """Weighted recall and precision of each kind, from ``refusals35._scores`` (gate weights)."""
    weight = {s["stratum"]: 1 / s["fraction"] for s in sample["strata"] if s["fraction"]}
    rows = [
        (weight[i["stratum"]], labels[i["item_id"]], kinds[i["claim_key"]])
        for i in sample["items"]
        if labels[i["item_id"]] != labelpage35.CANT_TELL
    ]
    out = {}
    for kind in claimkinds35.KINDS:
        scored = [
            (w, h == kind, None if p == claimkinds35.UNREADABLE else p == kind) for w, h, p in rows
        ]
        scores = refusals35._scores(scored)
        out[kind] = {
            "recall": _defined(scores["weighted_recall"]),
            "precision": _defined(scores["weighted_precision"]),
            "human": sum(h == kind for _, h, _ in rows),
            "predicted": sum(p == kind for _, _, p in rows),
        }
    return out


def score(found: Mapping[str, Any], out_dir: Path) -> int:
    """Write ``recheck-summary.json``; return 1 when a sample claim has no saved kind."""
    sample, labels = found["sample"], found["labels"]
    path = out_dir / "sample-kinds.jsonl"
    rows = read_rows(path) if path.is_file() else []
    kinds = {r["claim_key"]: r["kind"] for r in rows}
    missing = [i["claim_key"] for i in sample["items"] if i["claim_key"] not in kinds]
    versions = sorted({r["version"] for r in rows})
    if missing or len(versions) != 1:
        print(f"[recheck] {len(missing)} claims without a kind; versions {versions}", flush=True)
        return 1
    result = refusals35.gate(sample, labels, kinds, version=versions[0])
    summary = {
        "informational": True,
        "note": NOTE,
        "calls": len(sample["items"]),
        "excluded_examples": len(found["excluded"]),
        "unreadable_count": result["unreadable_count"],
        "gate": result,
        "per_kind": per_kind(sample, labels, kinds),
    }
    write_json(out_dir / "recheck-summary.json", summary)
    figures = {"classifier": result["classifier"], "per_kind": summary["per_kind"]}
    print(f"[recheck] informational: {json.dumps(figures, sort_keys=True)}", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--gate2", type=Path, required=True)
    p.add_argument("--examples", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name in ("split", "score"):
        s = sub.add_parser(name)
        s.add_argument("--input", type=Path, required=True)
        s.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        write_json(args.out, prepare(args.gate2, args.examples))
        return 0
    found = json.loads(args.input.read_text(encoding="utf-8"))
    if args.command == "split":
        write_json(args.out_dir / "sample.json", found["sample"])
        return 0
    return score(found, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
