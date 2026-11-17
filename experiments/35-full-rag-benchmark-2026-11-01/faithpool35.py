"""Faithfulness gate pool and draw (pre-registration section 11.2; task 15.8).

Moved out of ``labels35.py`` so that file stays under 500 lines; ``labels35``
re-exports every name. :func:`require_kinds` is the guard of ``labels35.py
sample``: the pool leaves out refusal claims, so each run folder it reads
must hold its saved claim kinds first.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import claimkinds35
import correct35
from outputs35 import Layout, read_rows

from omrs.core.answer.verify import split_claims

CORE = correct35.CORE
SEED_FAITH = 20261116
PER_CELL = 50


class KindsMissing(RuntimeError):
    """A run folder of the pool has no saved ``claim-kinds.jsonl``."""


def chunk_size(setup: str) -> int:
    """Return the chunk size in a setup name (``e4b-c1024-r4b-hon`` gives 1024)."""
    found = re.search(r"(?:^|-)c(\d+)(?:-|$)", setup)
    if found is None:
        raise ValueError(f"no chunk size in setup name {setup!r}")
    return int(found.group(1))


def _pool_answers(out_dir: Path) -> list[tuple[str, str, int, Path]]:
    """Return ``(dataset, setup, run, run folder)`` of the pool: core datasets, crossed setups.

    Raises:
        NoRunFiles: The output folder holds no answer run at all.
    """
    return [
        (dataset, setup, run, folder)
        for dataset, setup, run, folder in Layout(out_dir).need_runs("answer", "answer.jsonl")
        if dataset in CORE and "t20k" not in setup
    ]


def require_kinds(out_dir: Path) -> None:
    """Refuse when a run folder of the pool has no saved claim kinds.

    Raises:
        KindsMissing: The message names the first such run folder.
    """
    for dataset, setup, run, folder in _pool_answers(out_dir):
        if not (folder / "claim-kinds.jsonl").exists():
            raise KindsMissing(
                f"{dataset}/{setup}/run{run} has no claim-kinds.jsonl; "
                "run the claimkinds stage on it first"
            )


def faithfulness_claims(
    out_dir: Path, questions: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> list[dict[str, Any]]:
    """Return the faithfulness gate pool: crossed setups, core datasets, all runs and questions.

    A claim whose saved kind (``claim-kinds.jsonl`` of its own run folder) is
    ``refusal`` is left out. A claim of kind factual or mixed stays, and so
    does a claim the classifier left unclassified (no saved row, or kind
    ``unreadable``): section 12 treats it as factual (section 11.2).
    """
    claims: list[dict[str, Any]] = []
    for dataset, setup, run, folder in _pool_answers(out_dir):
        refusals = {
            r["claim_key"]
            for r in read_rows(folder / "claim-kinds.jsonl")
            if r["kind"] == "refusal"
        }
        for row in read_rows(folder / "answer.jsonl"):
            evidence = row.get("evidence") or []
            texts = {e["ordinal"]: e["text"] for e in evidence}
            for index, (claim, ordinals) in enumerate(
                split_claims(row.get("answer") or "", len(evidence))
            ):
                if claimkinds35.claim_key(row["qid"], claim) in refusals:
                    continue
                claims.append(
                    {
                        "item_id": correct35.item_id(
                            "faithfulness", dataset, setup, run, row["qid"], index
                        ),
                        "dataset": dataset,
                        "setup": setup,
                        "run": run,
                        "qid": row["qid"],
                        "index": index,
                        "chunk_size": chunk_size(setup),
                        "question": questions[dataset][row["qid"]]["question"],
                        "claim": claim,
                        "passages": [texts[o] for o in ordinals if o in texts],
                    }
                )
    return claims


def draw_faithfulness(
    claims: Sequence[Mapping[str, Any]], *, seed: int = SEED_FAITH, per_cell: int = PER_CELL
) -> list[dict[str, Any]]:
    """Draw ``per_cell`` claims per (chunk size, core dataset), at most one per answer, shuffled."""
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    cells: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for c in claims:
        cells[(c["chunk_size"], c["dataset"])].append(c)
    items: list[dict[str, Any]] = []
    for cell in sorted(cells):
        pool = sorted(cells[cell], key=lambda c: c["item_id"])
        rng.shuffle(pool)
        used: set[tuple[str, int, str]] = set()
        picked: list[dict[str, Any]] = []
        for c in pool:
            answer = (c["setup"], c["run"], c["qid"])
            if answer not in used and len(picked) < per_cell:
                used.add(answer)
                picked.append(dict(c))
        items += picked
    rng.shuffle(items)
    return items
