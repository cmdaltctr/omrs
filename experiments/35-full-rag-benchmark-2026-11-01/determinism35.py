"""G1 determinism stage of Experiment 35 (task 6.3; pre-registration section 15; A5 R-2).

``--stage determinism --setup <answer setup> --run <n>`` reads saved files only
and runs without the environment record. It needs no join (review S3): each
replicate pod runs it right after its answer stage, on its own
``run<n>/retrieval.jsonl`` and the search lists, so a G1 failure stops the run
before the paid judge and Ragas stages. For one answer setup and run:

1. Lists. For every question, the ranked list of 100 stored chunk IDs that
   answer run n saved (``run<n>/retrieval.jsonl``) must equal the list of the
   single search-stage run of the matching search setup
   (``search/<setup>/run1/search.jsonl``). Runs 1, 2 and 3 each match that one
   list, so they also match each other. A ``-t20k`` setup maps to its
   ``e?-c?-r?-hon`` search setup. A question whose search failed on either
   side (an empty list, a row closed as missing, or no row) is incomplete,
   never a match (``experiments/_lib/ranking.incomplete_comparisons``).
2. Evidence. The stored chunk IDs of each answer's evidence items must equal
   the head of that run's list under the setup's rule: 10 chunks, or the
   20,480-token cut on the saved token counts (``score35.token_cut_k``).

It writes ``<out>/<dataset>/answer/<setup>/run<n>/determinism.json`` with both
results and the run's machines (``machine.jsonl``), and returns 0 when G1
passes, else :data:`EXIT_MISMATCH`. A mismatch is recorded, never swapped for
another run. G1 passes for a setup when all three runs pass;
:func:`require_g1` is the guard of the confirmatory analysis.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import arms
import score35
import stages35
from experiments._lib.determinism import compare_runs
from experiments._lib.ranking import incomplete_comparisons
from outputs35 import Layout, read_rows, say, write_json

EXIT_MISMATCH = 3
RUNS = (1, 2, 3)


class G1NotPassed(RuntimeError):
    """A run of an answer setup has no passing ``determinism.json``."""


def require_g1(root: Path, setups: Mapping[str, Sequence[str]]) -> None:
    """Refuse unless every run of every answer setup passed G1.

    Args:
        root: The run output folder.
        setups: Per dataset with answers, its answer setups.

    Raises:
        G1NotPassed: Names the first run folder with no passing ``determinism.json``.
    """
    layout = Layout(root)
    for dataset, names in sorted(setups.items()):
        for setup in names:
            for run in RUNS:
                path = layout.run_dir(dataset, "answer", setup, run) / "determinism.json"
                found = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if found.get("ok") is not True:
                    raise G1NotPassed(f"{path}: G1 has not passed (run --stage determinism)")


def require_join(root: Path) -> None:
    """Refuse unless ``<root>/join.json`` passed and is not a smoke join.

    Raises:
        stages35.StageOrderError: Names the join step.
    """
    path = root / "join.json"
    found = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if found.get("ok") is not True:
        raise stages35.StageOrderError(f"{path} does not pass; run join35.py first")
    if found.get("smoke"):
        raise stages35.StageOrderError(f"{path} is a smoke join; G1 needs the main-run join")


def search_setup(setup: str) -> str:
    """Return the search setup whose single run an answer setup is compared with."""
    return arms.parse_setup(setup).name.removesuffix("-t20k")


def _lists(path: Path, qids: Sequence[str]) -> dict[str, list[str]]:
    """Return per frozen question the saved ranked chunk IDs; empty when failed or absent."""
    saved = {
        str(r["qid"]): [str(c["chunk_id"]) for c in r.get("chunks") or []] for r in read_rows(path)
    }
    return {q: saved.get(q, []) for q in qids}


def _rows(lists: Mapping[str, list[str]], label: str) -> list[dict[str, Any]]:
    return [
        {"question": q, "mode": "g1", "error": "" if ids else f"no ranked list in {label}"}
        for q, ids in lists.items()
    ]


def compare_lists(
    reference: Mapping[str, list[str]], runs: Mapping[str, Mapping[str, list[str]]]
) -> dict[str, Any]:
    """Compare each run's lists with the search lists; failed searches are incomplete.

    Returns:
        The ``compare_runs`` report of the complete questions plus ``incomplete``
        (``question_id``, ``reason``) and an ``ok`` that is False while one remains.
    """
    incomplete: dict[str, str] = {}
    for label, lists in runs.items():
        for row in incomplete_comparisons(_rows(reference, "search"), _rows(lists, label)):
            incomplete.setdefault(row["question"], row["incomplete"])
    sides = {"search": reference, **runs}
    report = compare_runs(
        {k: {q: ids for q, ids in v.items() if q not in incomplete} for k, v in sides.items()}
    ).to_dict()
    report["incomplete"] = [{"question_id": q, "reason": incomplete[q]} for q in sorted(incomplete)]
    report["ok"] = report["ok"] and not incomplete
    return report


def head(setup: str, chunks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the head of a ranked list under the setup's rule (10 chunks, or the token cut)."""
    k = score35.token_cut_k(chunks) if arms.parse_setup(setup).t20k else arms.TOP_K
    return [str(c["chunk_id"]) for c in chunks[:k]]


def evidence_ids(answer: Mapping[str, Any]) -> list[str]:
    """Return the stored chunk IDs an answer's evidence items hold, sorted."""
    ids: list[str] = []
    for item in answer.get("evidence") or []:
        ids += [str(i) for i in item.get("chunk_ids") or [item["chunk_id"]]]
    return sorted(ids)


def _evidence_mismatches(setup: str, run_dir: Path, run: int) -> list[dict[str, Any]]:
    chunks = {str(r["qid"]): r.get("chunks") or [] for r in read_rows(run_dir / "retrieval.jsonl")}
    found = []
    for answer in read_rows(run_dir / "answer.jsonl"):
        qid = str(answer["qid"])
        if answer.get("missing") or qid not in chunks:
            continue
        if evidence_ids(answer) != sorted(head(setup, chunks[qid])):
            found.append({"run": run, "question_id": qid})
    return found


async def determinism_stage(ctx: Any) -> int:
    """Check G1 for one answer setup and run; write ``run<n>/determinism.json``; return 0 or 3.

    Raises:
        stages35.StageOrderError: The search list, the run's answer file or its
            ``.done-answer.json`` (a finished answer stage) is missing (names it).
    """
    qids = [str(q.qid) for q in ctx.questions]
    source = search_setup(ctx.setup)
    search = ctx.layout.run_dir(ctx.dataset, "search", source, 1) / "search.jsonl"
    run_dir = ctx.layout.run_dir(ctx.dataset, "answer", ctx.setup, ctx.run)
    for path in (search, run_dir / "answer.jsonl", run_dir / ".done-answer.json"):
        if not path.exists():
            raise stages35.StageOrderError(f"G1 needs {path}; it is missing")
    reference = _lists(search, qids)
    lists = compare_lists(reference, {f"run{ctx.run}": _lists(run_dir / "retrieval.jsonl", qids)})
    evidence = _evidence_mismatches(ctx.setup, run_dir, ctx.run)
    report = {
        "ok": lists["ok"] and not evidence,
        "dataset": ctx.dataset,
        "setup": ctx.setup,
        "run": ctx.run,
        "search_setup": source,
        "lists": lists,
        "evidence_mismatches": evidence,
        "machines": read_rows(run_dir / "machine.jsonl"),
    }
    write_json(run_dir / "determinism.json", report)
    verdict = "passes" if report["ok"] else "FAILS"
    say(f"[determinism] {ctx.dataset}/{ctx.setup}/run{ctx.run}: G1 {verdict}")
    return 0 if report["ok"] else EXIT_MISMATCH
