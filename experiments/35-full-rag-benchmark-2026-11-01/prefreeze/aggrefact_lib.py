"""LLM-AggreFact loading, row order and leaderboard scoring (Exp 35 pre-freeze, task 6.5).

Pure helpers: this module reads only the files it is given and starts nothing.

Leaderboard rules (``lytang/LLM-AggreFact``): balanced accuracy per dataset,
label 1 (supported) is the positive class, then the plain mean over the
datasets. ``RAGTruth`` is one of the datasets. A row whose verdict is
``unparseable``, or whose request failed, counts as a wrong prediction: it is
never dropped, and the score keeps the count per dataset.

A dataset whose rows hold only one class has no balanced accuracy. The score
reports it as ``undefined``, leaves it out of the mean and adds a note.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

#: The verdict that predicts label 1. Pinned to ``omrs.core.answer.verify`` by a test.
SUPPORTED = "supported"
UNPARSEABLE = "unparseable"
#: Rows of the full TEST split.
EXPECTED_ROWS = 29320
#: SHA-256 of ``data/test-00000-of-00001.parquet`` at revision 981dfd0b (MANIFEST.json).
PARQUET_SHA256 = "ba6976c3da990a9d7b11670efaf4e3c93c1bd0530061ec742afd6b2d5bce698c"
#: The fixed shuffle seed of the row order.
SHUFFLE_SEED = 20261109
RAGTRUTH = "RAGTruth"
UNDEFINED = "undefined"
#: Published leaderboard values in points (design D13, read live 2026-11-08).
PUBLISHED: Mapping[str, Mapping[str, float]] = {
    "clef_flash": {"average": 76.6, RAGTRUTH: 83.2},
    "granite_guardian": {"average": 76.5, RAGTRUTH: 82.2},
}
COLUMNS = ("dataset", "doc", "claim", "label")


class ScoreError(ValueError):
    """A result file cannot be scored. The message is plain and holds no row text."""


def file_sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    """Return the SHA-256 of the file at *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Return the parquet rows in file order, each with its row index ``idx``.

    Raises:
        ScoreError: A required column is missing.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    missing = [name for name in COLUMNS if name not in table.column_names]
    if missing:
        raise ScoreError(f"{path.name} has no column {', '.join(missing)}")
    columns = {name: table.column(name).to_pylist() for name in COLUMNS}
    return [
        {"idx": idx, **{name: columns[name][idx] for name in COLUMNS}}
        for idx in range(table.num_rows)
    ]


def row_order(count: int, seed: int = SHUFFLE_SEED, limit: int | None = None) -> list[int]:
    """Return the row indexes in the fixed shuffled order, cut to *limit* when given.

    The same *count*, *seed* and *limit* always give the same list, so a limit
    run covers every dataset and a resumed run sees the same rows.
    """
    order = list(range(count))
    random.Random(seed).shuffle(order)  # noqa: S311 - a fixed order, not a secret
    return order if limit is None else order[:limit]


def predicted_supported(verdict: str | None) -> bool:
    """Return True when *verdict* predicts label 1 (``supported``)."""
    return verdict == SUPPORTED


def counted_wrong(row: Mapping[str, Any]) -> bool:
    """Return True for a row scored as wrong whatever its label: an error or ``unparseable``."""
    return row.get("error") is not None or row.get("verdict") in (UNPARSEABLE, None)


def prediction(row: Mapping[str, Any]) -> int:
    """Return the predicted label of *row*; an error or ``unparseable`` row gets the wrong one."""
    if counted_wrong(row):
        return 1 - int(row["label"])
    return 1 if predicted_supported(row["verdict"]) else 0


def dataset_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Return the confusion counts, errors and ``unparseable`` rows per dataset."""
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        item = counts.setdefault(
            str(row["dataset"]),
            {"rows": 0, "tp": 0, "tn": 0, "fp": 0, "fn": 0, "errors": 0, "unparseable": 0},
        )
        label, guess = int(row["label"]), prediction(row)
        key = {(1, 1): "tp", (0, 0): "tn", (0, 1): "fp", (1, 0): "fn"}[(label, guess)]
        item[key] += 1
        item["rows"] += 1
        if row.get("error") is not None:
            item["errors"] += 1
        elif row.get("verdict") in (UNPARSEABLE, None):
            item["unparseable"] += 1
    return counts


def balanced_accuracy(counts: Mapping[str, int]) -> float | None:
    """Return (TPR + TNR) / 2 in points (0 to 100), or ``None`` when a class is absent."""
    positives = counts["tp"] + counts["fn"]
    negatives = counts["tn"] + counts["fp"]
    if positives == 0 or negatives == 0:
        return None
    return 100.0 * (counts["tp"] / positives + counts["tn"] / negatives) / 2


def leaderboard(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the per-dataset scores, the plain mean and the RAGTruth value.

    Returns:
        ``datasets`` (counts plus ``balanced_accuracy``, a number or
        ``undefined``), ``average`` and ``RAGTruth`` (``None`` when not
        defined) and ``notes`` (one line per undefined dataset).
    """
    datasets: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    defined: dict[str, float] = {}
    for name, counts in sorted(dataset_counts(rows).items()):
        value = balanced_accuracy(counts)
        datasets[name] = {**counts, "balanced_accuracy": UNDEFINED if value is None else value}
        if value is None:
            notes.append(f"{name}: one class is absent, so it is left out of the mean")
        else:
            defined[name] = value
    average = sum(defined.values()) / len(defined) if defined else None
    return {
        "datasets": datasets,
        "average": average,
        RAGTRUTH: defined.get(RAGTRUTH),
        "datasets_in_mean": len(defined),
        "notes": notes,
    }


def pass_rule(
    avg: float,
    ragtruth: float,
    published_avg: float,
    published_ragtruth: float,
    tolerance: float = 1.0,
) -> dict[str, Any]:
    """Return the pass rule result: both values within *tolerance* points of the published ones.

    Gaps are rounded to 6 decimals first, so a gap of exactly 1.0 point passes
    despite float error.

    Returns:
        ``passed`` and the signed gaps ``average_gap`` and ``ragtruth_gap`` in points.
    """
    average_gap = round(avg - published_avg, 6)
    ragtruth_gap = round(ragtruth - published_ragtruth, 6)
    passed = abs(average_gap) <= tolerance and abs(ragtruth_gap) <= tolerance
    return {
        "passed": passed,
        "average_gap": average_gap,
        "ragtruth_gap": ragtruth_gap,
        "tolerance": tolerance,
    }


# --- result files ----------------------------------------------------------


def read_results(path: Path) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """Return the header, the first ``facts`` line (or ``None``) and the row lines of *path*.

    Raises:
        ScoreError: The file is empty, its first line is not a header, or a line is broken.
    """
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ScoreError(f"{path.name} is empty")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            raise ScoreError(f"{path.name} line {number} is not JSON") from None
    header = records[0]
    if header.get("kind") != "header":
        raise ScoreError(f"{path.name} does not start with a header line")
    facts = next((item for item in records if item.get("kind") == "facts"), None)
    rows = [item for item in records if item.get("kind") == "row"]
    return header, facts, rows


def check_complete(
    rows: Sequence[Mapping[str, Any]],
    expected: int | None = None,
    *,
    allow_partial: bool = False,
) -> bool:
    """Return True when the rows are partial (allowed); refuse a partial file otherwise.

    *expected* defaults to :data:`EXPECTED_ROWS`, read at call time.

    Raises:
        ScoreError: A row index repeats, or the file does not hold exactly
            *expected* distinct indexes and *allow_partial* is False.
    """
    expected = EXPECTED_ROWS if expected is None else expected
    indexes = [int(row["idx"]) for row in rows]
    distinct = set(indexes)
    if len(distinct) != len(indexes):
        raise ScoreError(f"{len(indexes) - len(distinct)} row indexes repeat in the result file")
    partial = len(distinct) != expected
    if partial and not allow_partial:
        raise ScoreError(
            f"the result file holds {len(distinct)} distinct rows, not {expected}; "
            "finish the run, or score with --allow-partial"
        )
    return partial


def score_results(
    header: Mapping[str, Any],
    facts: Mapping[str, Any] | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    expected: int | None = None,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Return the score summary of one strategy's result file.

    ``status`` is ``partial`` for a partial file, ``undefined`` when the
    average or RAGTruth is undefined, else ``pass`` or ``fail``.

    Raises:
        ScoreError: As :func:`check_complete`, or the strategy has no published value.
    """
    strategy = str(header.get("strategy"))
    if strategy not in PUBLISHED:
        raise ScoreError(f"no published value for strategy {strategy!r}")
    expected = EXPECTED_ROWS if expected is None else expected
    partial = check_complete(rows, expected, allow_partial=allow_partial)
    board = leaderboard(rows)
    published = PUBLISHED[strategy]
    rule = None
    if board["average"] is not None and board[RAGTRUTH] is not None:
        rule = pass_rule(
            board["average"], board[RAGTRUTH], published["average"], published[RAGTRUTH]
        )
    if partial:
        status = "partial"
    elif rule is None:
        status = UNDEFINED
    else:
        status = "pass" if rule["passed"] else "fail"
    facts = facts or {}
    return {
        "format": "omrs-aggrefact-score/1",
        "strategy": strategy,
        "status": status,
        "partial": partial,
        "rows_scored": len(rows),
        "expected_rows": expected,
        "rows_counted_wrong": sum(1 for row in rows if counted_wrong(row)),
        "published": dict(published),
        "pass_rule": rule,
        **board,
        "run": {
            key: header.get(key)
            for key in ("judge_version", "model", "parquet_sha256", "seed", "limit")
        },
        "judge_call": {key: facts.get(key) for key in ("model", "sha256", "version", "host")},
    }
