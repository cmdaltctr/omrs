"""Synthetic run folders for the Experiment 35 label and gate tests.

Each answer cites evidence with ``[n]`` markers so ``split_claims`` finds one
claim per sentence. Judge rows follow the stage layout: one verdict per claim,
in claim order, with its ``index``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write JSONL rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def answer_row(qid: str, sentences: Sequence[str]) -> dict[str, Any]:
    """An answer row whose claims are *sentences*, each citing passage 1."""
    text = " ".join(f"{s} [1]." for s in sentences)
    return {
        "qid": qid,
        "status": "ok",
        "answer": text,
        "evidence": [{"ordinal": 1, "text": f"passage for {qid}"}],
        "error": None,
    }


def judge_row(qid: str, verdicts: Sequence[str], judge: str = "chat") -> dict[str, Any]:
    """A judge row with one verdict per claim."""
    return {
        "qid": qid,
        "judge": judge,
        "verdicts": [{"index": i, "ordinals": [1], "verdict": v} for i, v in enumerate(verdicts)],
        "error": None,
    }


def write_run(
    run_dir: Path,
    answers: dict[str, Sequence[str]],
    verdicts: dict[str, dict[str, Sequence[str]]] | None = None,
) -> None:
    """Write ``answer.jsonl`` and one ``judge-<name>.jsonl`` per judge into *run_dir*.

    Args:
        run_dir: The run folder.
        answers: Question ID to claim sentences.
        verdicts: Judge name to (question ID to verdicts). Default: every
            claim supported by the ``chat`` judge.
    """
    write_rows(run_dir / "answer.jsonl", [answer_row(q, s) for q, s in answers.items()])
    if verdicts is None:
        verdicts = {"chat": {q: ["supported"] * len(s) for q, s in answers.items()}}
    for judge, per_q in verdicts.items():
        write_rows(
            run_dir / f"judge-{judge}.jsonl",
            [judge_row(q, v, judge) for q, v in per_q.items()],
        )
