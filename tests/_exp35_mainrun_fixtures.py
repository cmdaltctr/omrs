"""A synthetic main-run output folder for the Experiment 35 label tests.

Four datasets (the three core datasets and Legal), 100 questions each
(``q000`` to ``q099``; odd numbers in half B, so 50 per dataset). Answer
setups: two crossed setups per chunk size and one token-matched setup per
chunk size, runs 1 and 2. Every answer has two cited claims, judged by
``chat`` and ``clef_flash``. Each run 1 folder holds a ``ragas.jsonl`` row with
an ``answer_correctness`` score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests._exp35_label_fixtures import answer_row, judge_row, write_rows

DATASETS = ("bioasq", "financebench", "freshstack", "legal")
CHUNKS = (512, 1024, 2048)
SETUPS = tuple(
    name for c in CHUNKS for name in (f"e4b-c{c}-roff-hoff", f"e4b-c{c}-r4b-hon", f"e4b-c{c}-t20k")
)
QIDS = tuple(f"q{i:03d}" for i in range(100))


def build(out: Path) -> dict[str, Any]:
    """Write the folder, ``halves.json`` beside it, and return the questions mapping."""
    for dataset in DATASETS:
        for setup in SETUPS:
            for run in (1, 2):
                folder = out / dataset / setup / f"run{run}"
                answers = [answer_row(q, [f"Claim one of {q}", f"Claim two of {q}"]) for q in QIDS]
                write_rows(folder / "answer.jsonl", answers)
                for judge in ("chat", "clef_flash"):
                    write_rows(
                        folder / f"judge-{judge}.jsonl",
                        [judge_row(q, ["supported", "unsupported"], judge) for q in QIDS],
                    )
                if run == 1:
                    write_rows(
                        folder / "ragas.jsonl",
                        [
                            {"qid": q, "metrics": {"answer_correctness": {"score": (i % 10) / 10}}}
                            for i, q in enumerate(QIDS)
                        ],
                    )
    halves = {d: {q: ("B" if int(q[1:]) % 2 else "A") for q in QIDS} for d in DATASETS}
    (out.parent / "halves.json").write_text(json.dumps({"seed": 20261115, "halves": halves}))
    return {
        d: {q: {"question": f"{d} question {q}?", "reference": f"reference {q}"} for q in QIDS}
        for d in DATASETS
    }


def drop_legal(out: Path) -> None:
    """Record drop step 1 (Legal RAG Bench answer generation) in ``drops.json``."""
    (out / "drops.json").write_text(json.dumps({"drops": [{"step": 1, "reason": "ceiling"}]}))
