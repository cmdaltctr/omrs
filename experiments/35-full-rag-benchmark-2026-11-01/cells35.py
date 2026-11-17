"""Cell means and per-question contrasts of Experiment 35 (pre-registration sections 9 and 12).

Moved out of ``factorial35.py`` so that file stays under 500 lines;
``factorial35`` re-exports every name here.

Missing outcomes (section 12):

- A run with no value for a metric (an answer with no factual claim) is left
  out of the run mean; the cell mean uses the runs that have a value.
- A run whose checker or Ragas row closed missing names the metric in its
  ``unjudged`` list. That is not a no-claim run: the whole question-setup cell
  leaves the complete cases, and :func:`unjudged_cells` names it so the
  analysis can count it.
- A question enters a row only when every cell the row uses has a value.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import select35

Cells = Mapping[str, Mapping[str, float]]
CUT_TOKENS = "cut_tokens"
CUT_MIN = 19_456  # 95% of 20,480 tokens


def unjudged_cells(
    records: Iterable[Mapping[str, Any]], metric: str, field: str = "unjudged"
) -> dict[str, dict[str, set[str]]]:
    """Return per dataset and setup the questions with a run whose ``field`` list names ``metric``.

    ``field`` is ``unjudged`` (a closed-missing checker or Ragas row) or
    ``not_defined`` (a Ragas score that is NaN or no number).
    """
    found: dict[str, dict[str, set[str]]] = {}
    for row in records:
        if metric in (row.get(field) or ()):
            per = found.setdefault(row["dataset"], {}).setdefault(row["setup"], set())
            per.add(str(row["qid"]))
    return found


def cell_means(
    records: Iterable[Mapping[str, Any]], metric: str
) -> dict[str, dict[str, dict[str, float]]]:
    """Return per dataset, setup and question the mean of ``metric`` over runs that have it.

    A cell with an unjudged run gets no value (section 12).
    """
    rows = list(records)
    unjudged = unjudged_cells(rows, metric)
    values: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        key = (row["dataset"], row["setup"], str(row["qid"]))
        bucket = values.setdefault(key, [])
        if row.get(metric) is not None:
            bucket.append(float(row[metric]))
    cells: dict[str, dict[str, dict[str, float]]] = {}
    for (dataset, setup, qid), found in values.items():
        per_setup = cells.setdefault(dataset, {}).setdefault(setup, {})
        if found and qid not in unjudged.get(dataset, {}).get(setup, set()):
            per_setup[qid] = math.fsum(found) / len(found)
    return cells


def stage_setups(stage: str, cells: Cells) -> list[str]:
    """Return the setups of ``cells`` that belong to ``stage`` (search, crossed or t20k)."""
    if stage == "search":
        return sorted(cells)
    want = stage == "t20k"
    return sorted(s for s in cells if select35.parse_setup(s).t20k == want)


def groups(row: Any, cells: Cells) -> list[tuple[float, list[str]]]:
    """Return each term of ``row`` with the saved setups of its stage that match it."""
    setups = stage_setups(row.stage, cells)
    grid = {s: select35.parse_setup(s) for s in setups}
    return [
        (coefficient, [s for s in setups if all(getattr(grid[s], k) in v for k, v in lv.items())])
        for coefficient, lv in row.terms
    ]


def contrast(
    row: Any, cells: Cells, questions: Sequence[str] | None = None
) -> tuple[dict[str, float], int]:
    """Return the per-question contrast scores d of ``row`` and the excluded count.

    A question enters only when every cell the row uses has a value.

    Args:
        row: A contrast-table row (``terms`` and ``stage``).
        cells: Per setup and question, the cell value.
        questions: Every question of the dataset. The excluded count is
            measured against it, so a question with no value in any cell
            counts too. When absent, the questions with a value in at least
            one stage cell.
    """
    setups = stage_setups(row.stage, cells)
    terms = groups(row, cells)
    used = sorted({s for _, match in terms for s in match})
    every = set().union(*(cells[s] for s in setups)) if setups else set()
    if questions is not None:
        every = set(questions)
    entered = [q for q in sorted(every) if all(q in cells[s] for s in used)]
    d = {
        q: math.fsum(c * math.fsum(cells[s][q] for s in m) / len(m) for c, m in terms)
        for q in entered
    }
    return d, len(every) - len(entered)


def documents(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Return per dataset the document of each question; a record with no ``doc_id`` is skipped.

    A closed-missing answer row may lack the document, and it must not move its
    question to a cluster named ``None``.
    """
    docs: dict[str, dict[str, str]] = {}
    for row in records:
        if row.get("doc_id") is not None:
            docs.setdefault(row["dataset"], {})[str(row["qid"])] = str(row["doc_id"])
    return docs


def _cut_totals(answers: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Return per dataset, question and t20k setup the cut total of any run that saved one."""
    seen: dict[str, dict[str, dict[str, Any]]] = {}
    for row in answers:
        if select35.parse_setup(row["setup"]).t20k:
            per = seen.setdefault(row["dataset"], {}).setdefault(str(row["qid"]), {})
            if per.get(row["setup"]) is None:
                per[row["setup"]] = row.get(CUT_TOKENS)
    return seen


def h8b_questions(answers: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Return per dataset the questions whose cut total is at least 19,456 in every t20k setup.

    The cut total comes from the search lists, so every run of a setup holds the
    same one (G1); a closed-missing answer row has none and another run gives it.
    A question with no cut total in some t20k setup is left out.
    """
    totals = _cut_totals(answers)
    setups = {d: {s for per in q.values() for s in per} for d, q in totals.items()}
    return {
        d: {
            qid
            for qid, per in q.items()
            if all(per.get(s) is not None and per[s] >= CUT_MIN for s in setups[d])
        }
        for d, q in totals.items()
    }


def no_cut_total(answers: Sequence[Mapping[str, Any]], dataset: str) -> int:
    """Return how many questions of *dataset* lack a cut total in some t20k setup."""
    totals = _cut_totals(answers).get(dataset, {})
    setups = {s for per in totals.values() for s in per}
    return sum(1 for per in totals.values() if any(per.get(s) is None for s in setups))


def excluded_counts(
    row: Any, cells: Cells, d: Mapping[str, float], questions: Sequence[str], marks: Any
) -> dict[str, int]:
    """Count the questions ``row`` left out (section 12), each in one category.

    Unjudged: a cell the row uses has an unjudged run. Not defined: otherwise, a
    cell has a run with an undefined Ragas score. No value: the rest (no claim).
    """
    used = {s for _, match in groups(row, cells) for s in match}
    left = [q for q in questions if q not in d]

    def hit(kind: str, q: str) -> bool:
        return any(q in marks[kind].get(s, ()) for s in used)

    unjudged = [q for q in left if hit("unjudged", q)]
    undefined = [q for q in left if q not in unjudged and hit("not_defined", q)]
    return {
        "excluded_unjudged": len(unjudged),
        "excluded_not_defined": len(undefined),
        "excluded_no_value": len(left) - len(unjudged) - len(undefined),
    }
