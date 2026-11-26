"""Registered report outputs of Experiment 35 that ``reporttables35`` adds (review S4).

Pre-registration sections 6, 11.3 and 21. Each function reads saved files or
records only; a value that is not defined reads :data:`NOT_DEFINED`.

- :func:`number_match_table`: FinanceBench number match per answer setup
  (``scoring35.number_match``). A missing or empty answer scores 0 on a scored
  question; a reference that holds no number is not scored and leaves the
  denominator. Scores average over the runs, then over the scored questions.
- :func:`uncited_sensitivity`: the faithfulness rows 12, 13, 16 and 17 on
  ``faithfulness_glm_factual_uncited`` (uncited factual segments count as
  unsupported) by the section 9 method, beside the uncited-segment share.
  Descriptive; it changes no decision.
- :func:`compute_table`: pod hours and cost per stage and run mode from the
  run records of each pod. A record's hours run from its start to the next
  start on the same pod (billed pod time, idle time included); the last
  record of a pod has no end, so its hours are not defined. Cost uses the
  pod price of the budget rates file (``pod_usd_per_hour``, ``budget35``).
- :func:`fenced_rows`: per file extension, the files, fenced files, corpus
  rows and fenced rows of the FreshStack export (``prepare35`` manifest).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import cells35
import datasets35
import factorial35
import scoring35
from outputs35 import Layout, read_rows

NOT_DEFINED = "not defined"
UNCITED = "faithfulness_glm_factual_uncited"
FB = "financebench"
_STAGE = re.compile(r"--stage\s+(\S+)")


def _match(reference: str, answer: Mapping[str, Any] | None) -> int:
    if answer is None or answer.get("missing") or not answer.get("answer"):
        return 0  # section 12: a missing or empty answer scores 0 on a scored question
    return int(bool(scoring35.number_match(reference, answer["answer"])))


def number_match_table(out: Path, references: Mapping[str, str]) -> dict[str, Any]:
    """Return per FinanceBench answer setup the number match over the scored questions."""
    scored = {q: r for q, r in references.items() if scoring35.extract_numbers(r)}
    runs: dict[str, list[dict[str, Mapping[str, Any]]]] = {}
    for _, setup, _, folder in Layout(out).runs("answer", "answer.jsonl", dataset=FB):
        runs.setdefault(setup, []).append(
            {str(r["qid"]): r for r in read_rows(folder / "answer.jsonl")}
        )
    table: dict[str, Any] = {}
    for setup, answers in sorted(runs.items()):
        means = [
            math.fsum(_match(ref, run.get(q)) for run in answers) / len(answers)
            for q, ref in sorted(scored.items())
        ]
        table[setup] = {
            "runs": len(answers),
            "scored_questions": len(means),
            "not_scored": len(references) - len(scored),
            "number_match": math.fsum(means) / len(means) if means else NOT_DEFINED,
        }
    return table


def load_references(root: Path | None = None) -> dict[str, str]:
    """Return the FinanceBench reference answer per question from the data folder."""
    found = datasets35.load_questions(FB, root or datasets35.data_root())
    return {q.qid: q.reference for q in found}


def uncited_sensitivity(
    answers: Sequence[Mapping[str, Any]],
    share: Mapping[str, Any],
    *,
    n_draws: int = factorial35.stats_cluster.SIGN_FLIP_DRAWS,
) -> dict[str, Any]:
    """Return per dataset the faithfulness rows on the uncited value, beside the uncited share."""
    cells = cells35.cell_means(answers, UNCITED)
    docs = cells35.documents(answers)
    out: dict[str, Any] = {}
    for dataset in sorted(cells):
        rows = []
        for row in factorial35.ROWS:
            if row.outcome != "faithfulness":
                continue
            d, _ = cells35.contrast(row, cells[dataset])
            test = (
                factorial35._test(dataset, d, docs.get(dataset, {}), n_draws)
                if len(d) > 1
                else {"estimate": NOT_DEFINED}
            )
            rows.append({"row": row.number, "metric": UNCITED, "n": len(d), **test})
        out[dataset] = {"rows": rows, "uncited_segment_share": share.get(dataset, NOT_DEFINED)}
    return out


def _start(record: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(record["started_at"]).replace("Z", "+00:00"))


def _stage(command: str) -> str:
    found = _STAGE.search(command)
    return found.group(1) if found else Path(command.split()[0]).name if command else "unknown"


def _mode(record: Mapping[str, Any]) -> str:
    return "prefreeze" if record.get("prefreeze") else "smoke" if record.get("smoke") else "main"


def compute_table(
    pods: Mapping[str, Sequence[Mapping[str, Any]]], usd_per_hour: float | None
) -> dict[str, Any]:
    """Return pod hours and cost per run mode and stage from each pod's run records."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for _, lines in sorted(pods.items()):
        ordered = sorted(lines, key=_start)
        for line, later in zip(ordered, [*ordered[1:], None], strict=True):
            key = (_mode(line), _stage(str(line.get("command") or "")))
            per = found.setdefault(key, {"runs": 0, "hours": 0.0, "open_ended_runs": 0})
            per["runs"] += 1
            if later is None:
                per["open_ended_runs"] += 1
            else:
                per["hours"] += (_start(later) - _start(line)).total_seconds() / 3600
    rows = []
    for (mode, stage), per in sorted(found.items()):
        hours = NOT_DEFINED if per["open_ended_runs"] else per["hours"]
        cost = NOT_DEFINED if usd_per_hour is None or hours == NOT_DEFINED else hours * usd_per_hour
        rows.append(
            {
                "mode": mode,
                "stage": stage,
                "runs": per["runs"],
                "open_ended_runs": per["open_ended_runs"],
                "pod_hours": hours,
                "closed_pod_hours": per["hours"],
                "usd": cost,
            }
        )
    price = NOT_DEFINED if usd_per_hour is None else usd_per_hour
    return {"pod_usd_per_hour": price, "stages": rows}


def fenced_rows(passages_dir: Path) -> dict[str, Any] | str:
    """Return per extension the FreshStack files, fenced files, rows and fenced rows."""
    path = passages_dir / "freshstack" / datasets35.MANIFEST_FILE
    if not path.is_file():
        return NOT_DEFINED
    table: dict[str, dict[str, int]] = {}
    for row in read_rows(path):
        per = table.setdefault(
            str(row["extension"]), {"files": 0, "fenced_files": 0, "rows": 0, "fenced_rows": 0}
        )
        fenced, count = bool(row["fenced"]), int(row["rows"])
        per["files"] += 1
        per["fenced_files"] += fenced
        per["rows"] += count
        per["fenced_rows"] += count if fenced else 0
    return dict(sorted(table.items()))


def pod_records(paths: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    """Return each pod's run-record lines, keyed by the record file's stem."""
    return {p.stem: read_rows(p) for p in paths}
