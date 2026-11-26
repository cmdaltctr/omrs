"""Floor, ceiling and retrieval-miss cross-table of Experiment 35 (task 15.16; PR 13).

Usage (reads saved files only; runs without the environment record)::

    crosstable35.py --out-dir OUT

Inputs: ``<out>/answer-scores.jsonl`` (``join35.py``), the score records of
``score35.py`` (``<out>/scores/<half>/<dataset>/<search setup>.jsonl``, both
halves) and the single-run folders ``<out>/<dataset>/<kind>/<setup>/run1/``
of ``closedbook-own`` (floor), ``closedbook-rag`` and ``oracle`` (ceiling).

Writes ``<out>/crosstable.json``:

- ``floor_ceiling``: per dataset, mean Ragas correctness per RAG answer setup
  (``runs: 3``, the per-question mean over runs first) and per single-run
  kind (``runs: 1``, ``single_run: true``); descriptive only.
- ``miss_crosstable``: per dataset and RAG answer setup, over the questions
  that setup's retrieval missed, the counts of closed-book (own-knowledge)
  correct or not against RAG correct or not. "Correct" is Ragas correctness
  at least 0.5 (the RAG value is the mean over runs). A retrieval miss is a
  question with no gold unit in the evidence: ``evidence_recall_20k`` of 0 for
  a ``-t20k`` setup, ``head_recall_10`` (units of the first 10 stored chunks,
  the 10-chunk evidence) of 0 for a 10-chunk setup, both from the
  matching search setup's score record. ``misses_total`` counts every miss;
  ``no_rag_score`` (every run unjudged) and ``no_closed_book_score`` count
  the misses that leave the table for want of a score (section 12).

``main`` runs behind the half-B guard: the tables hold half-B scores.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
import joinscores35  # noqa: E402
import scoring35  # noqa: E402
from cells35 import cell_means  # noqa: E402
from outputs35 import Layout, NoRunFiles, read_rows, write_json  # noqa: E402

CUT = 0.5
SINGLE_RUN = ("closedbook-own", "closedbook-rag", "oracle")
FLOOR = "closedbook-own"
CORRECT = "ragas_answer_correctness"


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _single_runs(out: Path) -> dict[str, dict[str, dict[str, float]]]:
    """Return per dataset and single-run kind the correctness per question (first setup folder)."""
    found: dict[str, dict[str, dict[str, float]]] = {}
    for kind in SINGLE_RUN:
        first: dict[str, Path] = {}
        for dataset, _, run, folder in Layout(out).runs(kind, "answer.jsonl"):
            if run == 1:
                first.setdefault(dataset, folder)
        for dataset, folder in sorted(first.items()):
            # Correctness only: no claim kind is read.
            records = joinscores35.answer_scores(folder, dataset, kind, 1, kinds_version=None)
            found.setdefault(dataset, {})[kind] = {
                r["qid"]: r[CORRECT] for r in records if r[CORRECT] is not None
            }
    return found


def _misses(out: Path, dataset: str, setup: str) -> set[str]:
    factors = arms.parse_setup(setup)
    metric = "evidence_recall_20k" if factors.t20k else "head_recall_10"
    search = factors.name.removesuffix("-t20k")
    rows = [
        r
        for half in ("A", "B")
        for r in read_rows(out / "scores" / half / dataset / f"{search}.jsonl")
    ]
    return {str(r["qid"]) for r in rows if r[metric] == 0}


def build_tables(out: Path) -> dict[str, Any]:
    """Return the floor and ceiling table and the retrieval-miss cross-table.

    Raises:
        NoRunFiles: ``answer-scores.jsonl`` is missing or empty (no passing join).
    """
    scores = read_rows(out / "answer-scores.jsonl")
    if not scores:
        raise NoRunFiles(f"{out / 'answer-scores.jsonl'} is missing or empty; run join35.py first")
    rag = cell_means(scores, CORRECT)  # an unjudged run drops the cell (section 12)
    single = _single_runs(out)
    floor_ceiling: dict[str, list[dict[str, Any]]] = {}
    cross: dict[str, dict[str, dict[str, int]]] = {}
    for dataset in sorted(set(rag) | set(single)):
        rows = [
            {
                "kind": "rag",
                "setup": s,
                "runs": 3,
                "single_run": False,
                "correctness": _mean(list(v.values())),
                "n": len(v),
            }
            for s, v in sorted(rag.get(dataset, {}).items())
        ]
        rows += [
            {
                "kind": k,
                "setup": None,
                "runs": 1,
                "single_run": True,
                "correctness": _mean(list(v.values())),
                "n": len(v),
            }
            for k, v in sorted(single.get(dataset, {}).items())
        ]
        floor_ceiling[dataset] = rows
        floor = single.get(dataset, {}).get(FLOOR, {})
        for setup, scores in sorted(rag.get(dataset, {}).items()):
            missed = _misses(out, dataset, setup)
            misses = sorted(missed & set(scores) & set(floor))
            counts = dict.fromkeys(
                (
                    f"closed_book_{c}_rag_{r}"
                    for c in ("correct", "wrong")
                    for r in ("correct", "wrong")
                ),
                0,
            )
            for qid in misses:
                book = "correct" if floor[qid] >= CUT else "wrong"
                answer = "correct" if scores[qid] >= CUT else "wrong"
                counts[f"closed_book_{book}_rag_{answer}"] += 1
            cross.setdefault(dataset, {})[setup] = {
                "misses_total": len(missed),
                "no_rag_score": len(missed - set(scores)),
                "no_closed_book_score": len(missed - set(floor)),
                "misses": len(misses),
                **counts,
            }
    return {"cut": CUT, "floor_ceiling": floor_ceiling, "miss_crosstable": cross}


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<out>/crosstable.json``; return 0."""
    parser = argparse.ArgumentParser(prog="crosstable35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the joined output folder")
    args = parser.parse_args(argv)
    scoring35.require_half_b(args.out_dir)  # the table holds half-B scores (section 14.2)
    write_json(args.out_dir / "crosstable.json", build_tables(args.out_dir))
    print(f"[crosstable] {args.out_dir / 'crosstable.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
