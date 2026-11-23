"""Contamination sensitivity of Experiment 35 (task 15.4 report part; pre-registration section 13).

Usage (reads saved files only; runs on the Mac)::

    contamination35.py --out-dir OUT [--draws N]

A registered sensitivity analysis, never decisive. The correctness rows 14, 15,
18 and 19 run again, with the registered test of section 9, on the questions
that both closed-book runs answer wrongly: Ragas correctness below 0.5 in the
own-knowledge run (``closedbook-own``) and in the RAG-prompt run
(``closedbook-rag``). A score of exactly 0.5 counts as correct. A question with
no closed-book score in a run the subset needs is left out and counted
(``no_closed_book_score``).

When drop step 3 (``drops.json``, section 17) removed the RAG-prompt run, the
subset uses the own-knowledge run alone, and the table is labelled
"one closed-book run".

Inputs: ``<out>/answer-scores.jsonl`` (``join35.py``) and the closed-book run
folders that ``crosstable35.py`` reads. Writes ``<out>/contamination.json``.
The table holds half-B scores, so ``main`` runs behind the half-B guard.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import budget35  # noqa: E402
import crosstable35  # noqa: E402
import factorial35  # noqa: E402
import scoring35  # noqa: E402
from experiments._lib import stats_cluster  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

ROWS = (14, 15, 18, 19)
CUT = 0.5
OWN, RAG = "closedbook-own", "closedbook-rag"
RAG_PROMPT_DROP = 3  # budget35.DROP_STEPS[3]: the closed-book run with the RAG prompt
LABELS = {1: "one closed-book run", 2: "two closed-book runs"}


def wrong_subset(
    closed: Mapping[str, Mapping[str, float]], questions: Iterable[str], rag_dropped: bool
) -> tuple[set[str], int, list[str]]:
    """Return the questions every used closed-book run answers wrongly.

    Args:
        closed: Per closed-book kind, the Ragas correctness per question.
        questions: Every question of the dataset.
        rag_dropped: True when drop step 3 removed the RAG-prompt run.

    Returns:
        The subset, the count of questions with no score in a used run, and the runs used.
    """
    runs = [OWN] if rag_dropped else [OWN, RAG]
    subset, unscored = set(), 0
    for qid in questions:
        scores = [closed.get(kind, {}).get(qid) for kind in runs]
        if any(s is None for s in scores):
            unscored += 1
        elif all(s < CUT for s in scores):
            subset.add(qid)
    return subset, unscored, runs


def contamination(
    answer_records: Sequence[Mapping[str, Any]],
    closed_book: Mapping[str, Mapping[str, Mapping[str, float]]],
    drops: Collection[int],
    *,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
) -> dict[str, dict[str, Any]]:
    """Return per dataset the correctness rows 14, 15, 18 and 19 on the closed-book-wrong subset.

    Args:
        answer_records: Per-question answer score records, one per run (``factorial35`` shape).
        closed_book: Per dataset and closed-book kind, the correctness per question.
        drops: The drop steps recorded in ``drops.json``.
        n_draws: FinanceBench sign-flip draws (100,000 registered).
    """
    cells = factorial35.cell_means(answer_records, factorial35.CORRECT)
    docs = factorial35.documents(answer_records)
    every = factorial35._questions(answer_records)
    rag_dropped = RAG_PROMPT_DROP in drops
    out: dict[str, dict[str, Any]] = {}
    for dataset in sorted(cells):
        questions = every[dataset]  # the subset needs closed-book scores, not RAG scores
        subset, unscored, runs = wrong_subset(closed_book.get(dataset, {}), questions, rag_dropped)
        kept = sorted(subset)
        rows = []
        for number in ROWS:
            row = factorial35.ROWS[number - 1]
            d, excluded = factorial35.contrast(row, cells[dataset], kept)
            test = factorial35._test(dataset, d, docs.get(dataset, {}), n_draws) if d else {}
            rows.append(
                {
                    "row": number,
                    "hypothesis": row.hypothesis,
                    "metric": factorial35.CORRECT,
                    "n": len(d),
                    "excluded": excluded,
                    **(test or {"estimate": math.nan, "p_value": math.nan}),
                }
            )
        out[dataset] = {
            "label": LABELS[len(runs)],
            "runs": runs,
            "cut": CUT,
            "questions": len(questions),
            "questions_kept": len(kept),
            "no_closed_book_score": unscored,
            "rows": rows,
        }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<out>/contamination.json``; return 0."""
    parser = argparse.ArgumentParser(prog="contamination35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the joined output folder")
    parser.add_argument("--draws", type=int, default=stats_cluster.SIGN_FLIP_DRAWS)
    args = parser.parse_args(argv)
    scoring35.require_half_b(args.out_dir)  # the table holds half-B scores (section 14.2)
    closed = crosstable35._single_runs(args.out_dir)
    table = contamination(
        read_rows(args.out_dir / "answer-scores.jsonl"),
        closed,
        budget35.read_drops(args.out_dir),
        n_draws=args.draws,
    )
    write_json(args.out_dir / "contamination.json", table)
    print(f"[contamination] {args.out_dir / 'contamination.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
