"""Confirmatory analysis command of Experiment 35 (review B1; pre-registration 7 to 9, 14 and 15).

Usage (reads saved files only; runs on the Mac after the main join)::

    analyse35.py --out-dir OUT --halves HALVES --label-dir LABELS --gate GATE

In this order:

1. ``scoring35.require_half_b(OUT)`` before any read (section 14.2).
2. G1: every run of every answer setup has a passing ``determinism.json``
   (``determinism35.require_g1``, section 15).
3. The search score records of both halves (``scores/A|B/<dataset>/<setup>.jsonl``,
   ``score35.py``). Each question of a dataset's ``halves.json`` list appears
   exactly once per setup, and no other question appears.
4. ``answer-scores.jsonl`` of the main join.
5. ``factorial35.write_confirmatory`` (gate files in LABELS, classifier gate 3
   in GATE, the join and the drop record) writes ``OUT/confirmatory.json``;
   the RQ1 headline (section 14.3, the A3 cell of ``selection.json`` on half
   B) and the descriptive 72-setup table are added to the same file. When
   classifier gate 3 has not passed (amendment A14), the faithfulness headline
   is descriptive only: ``faithfulness_glm_factual_descriptive`` holds the
   half-B mean and ``n``, with no interval and no p-value.

``reporttables35.py --factorial OUT/confirmatory.json`` reads that file. Exit
codes: 0 written; 2 a guard refused (the message names the reason; nothing
is written).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
import budget35  # noqa: E402
import cells35  # noqa: E402
import determinism35  # noqa: E402
import factorial35  # noqa: E402
import kindgate35  # noqa: E402
import labels35  # noqa: E402
import scoring35  # noqa: E402
import select35  # noqa: E402
import stages35  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

RESULT = "confirmatory.json"
DESCRIPTIVE_FAITH = f"{factorial35.FAITH}_descriptive"


class AnalysisError(RuntimeError):
    """An input of the analysis is missing or does not hold each question once."""


def search_records(out: Path, halves: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    """Return the search score records of both halves; each frozen question once per setup.

    Raises:
        AnalysisError: No record, a question twice in a setup, or a setup whose
            questions differ from the dataset's ``halves.json`` list (names the
            dataset, setup and question).
    """
    rows: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], set[str]] = {}
    for path in sorted((out / "scores").glob("[AB]/*/*.jsonl")):
        for row in read_rows(path):
            qids = seen.setdefault((row["dataset"], row["setup"]), set())
            if str(row["qid"]) in qids:
                raise AnalysisError(f"{row['dataset']}/{row['setup']}: question {row['qid']} twice")
            qids.add(str(row["qid"]))
            rows.append(row)
    if not rows:
        raise AnalysisError(f"{out / 'scores'} holds no search score record; run score35.py")
    for (dataset, setup), qids in sorted(seen.items()):
        frozen = set(halves.get(dataset, {}))
        if qids != frozen:
            missing, extra = sorted(frozen - qids), sorted(qids - frozen)
            if missing:
                raise AnalysisError(f"{dataset}/{setup}: no search score for question {missing[0]}")
            raise AnalysisError(f"{dataset}/{setup}: question {extra[0]} is not in halves.json")
    return rows


def descriptive_headline(
    records: Sequence[Mapping[str, Any]],
    setup: str,
    metric: str,
    halves: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, Any]]:
    """Return ``setup``'s half-B mean ``metric`` per core dataset, with no interval or p-value."""
    cells = cells35.cell_means(records, metric)
    out = {}
    for dataset in select35.CORE:
        found = cells.get(dataset, {}).get(setup, {})
        scores = [v for q, v in found.items() if halves[dataset].get(q) == "B"]
        mean = math.fsum(scores) / len(scores) if scores else None
        out[dataset] = {
            "setup": setup,
            "metric": metric,
            "half": "B",
            "n": len(scores),
            "mean": mean,
            "descriptive": True,
        }
    return out


def answer_setups(out: Path) -> dict[str, list[str]]:
    """Return per dataset with answers (after the drop record) the 15 answer setups."""
    chosen = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    names = [s.name for s in arms.answer_setups(chosen["embedder"], chosen["reranker"])]
    return {d: names for d in budget35.answer_datasets(budget35.read_drops(out))}


def analyse(
    out: Path, halves_path: Path, label_dir: Path, gate: Path | None, **draws: int
) -> dict[str, Any]:
    """Run steps 1 to 5 of the module docstring; return the written record."""
    scoring35.require_half_b(out)
    determinism35.require_g1(out, answer_setups(out))
    halves = json.loads(halves_path.read_text(encoding="utf-8"))["halves"]
    search = search_records(out, halves)
    if not (out / "answer-scores.jsonl").is_file():
        raise AnalysisError(f"{out / 'answer-scores.jsonl'} is missing; run join35.py first")
    answers = read_rows(out / "answer-scores.jsonl")
    path = out / RESULT
    result = factorial35.write_confirmatory(
        path, search, answers, label_dir=label_dir, root=out, kind_gate=gate, **draws
    )
    cell = json.loads((out / "selection.json").read_text(encoding="utf-8"))["cell"]
    n_draws = draws.get("n_draws", factorial35.stats_cluster.SIGN_FLIP_DRAWS)
    saved = json.loads(path.read_text(encoding="utf-8"))
    faith, correct = factorial35.FAITH, factorial35.CORRECT
    if saved["classifier_gate"]["pass"]:
        answer = {faith: factorial35.headline(answers, cell, faith, halves, n_draws=n_draws)}
    else:  # amendment A14: faithfulness over every cited claim is descriptive only
        answer = {DESCRIPTIVE_FAITH: descriptive_headline(answers, cell, faith, halves)}
    answer[correct] = factorial35.headline(answers, cell, correct, halves, n_draws=n_draws)
    record = {
        **saved,
        "headline": {
            "retrieval": factorial35.headline(
                search, cell, factorial35.NDCG, halves, n_draws=n_draws
            ),
            "answer": answer,
        },
        "setup_table": factorial35.setup_table(search),
    }
    write_json(path, record)
    return {**result, **record}


REFUSALS = (
    scoring35.HalfBLocked,
    determinism35.G1NotPassed,
    stages35.StageOrderError,
    labels35.GateMissing,
    kindgate35.KindGateError,
    AnalysisError,
)


def main(argv: Sequence[str] | None = None, **draws: int) -> int:
    """Write ``<out>/confirmatory.json``; return 0, or 2 when a guard refuses."""
    parser = argparse.ArgumentParser(prog="analyse35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the joined output folder")
    parser.add_argument("--halves", type=Path, required=True, help="halves.json")
    parser.add_argument("--label-dir", type=Path, required=True, help="the gate files' folder")
    parser.add_argument("--gate", type=Path, help="classifier gate 3 gate.json (refusals35.py)")
    args = parser.parse_args(argv)
    try:
        analyse(args.out_dir, args.halves, args.label_dir, args.gate, **draws)
    except REFUSALS as error:
        print(f"[analyse] refused: {error}", file=sys.stderr, flush=True)
        return 2
    print(f"[analyse] {args.out_dir / RESULT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
