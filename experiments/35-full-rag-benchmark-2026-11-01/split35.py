"""Halves A and B for Experiment 35 (pre-registration section 4, readiness task 15.5).

FinanceBench is split by document: documents are shuffled with the seed, and
each goes, with all its questions, to the half with fewer questions so far
(ties to A). The other datasets are split by question: questions are shuffled
with the seed, and the first half (rounded up) is half A.

The shuffle is ``random.Random(seed).shuffle`` on the sorted IDs, with a fresh
generator per dataset. The caller loads the question IDs (and the FinanceBench
document of each question) and calls ``make_halves`` then ``write_halves``.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections.abc import Mapping, Sequence
from pathlib import Path

SEED = 20261115
DOCUMENT_SPLIT = "financebench"
HALVES = ("A", "B")

Halves = dict[str, dict[str, str]]


def split_by_question(question_ids: Sequence[str], seed: int = SEED) -> dict[str, str]:
    """Shuffle question IDs with ``seed``; the first half, rounded up, is half A.

    Args:
        question_ids: Question IDs of one dataset.
        seed: Shuffle seed.

    Returns:
        Half (``A`` or ``B``) per question ID.
    """
    ids = sorted(set(question_ids))
    random.Random(seed).shuffle(ids)  # noqa: S311 - seeded split, not security
    cut = (len(ids) + 1) // 2
    return {qid: "A" if i < cut else "B" for i, qid in enumerate(ids)}


def assign_documents(ordered: Sequence[tuple[str, Sequence[str]]]) -> dict[str, str]:
    """Send each document, in the given order, to the half with fewer questions so far.

    Ties go to A.

    Args:
        ordered: (document ID, its question IDs) in shuffled order.

    Returns:
        Half per question ID.
    """
    counts = {"A": 0, "B": 0}
    halves: dict[str, str] = {}
    for _, questions in ordered:
        half = "A" if counts["A"] <= counts["B"] else "B"
        counts[half] += len(questions)
        halves.update({qid: half for qid in questions})
    return halves


def split_by_document(documents: Mapping[str, str], seed: int = SEED) -> dict[str, str]:
    """Split by document: shuffle documents with ``seed``, then ``assign_documents``.

    Args:
        documents: Document ID per question ID.
        seed: Shuffle seed.

    Returns:
        Half per question ID.
    """
    by_document: dict[str, list[str]] = {}
    for qid in sorted(documents):
        by_document.setdefault(documents[qid], []).append(qid)
    names = sorted(by_document)
    random.Random(seed).shuffle(names)  # noqa: S311 - seeded split, not security
    return assign_documents([(name, by_document[name]) for name in names])


def make_halves(questions: Mapping[str, Mapping[str, str | None]], seed: int = SEED) -> Halves:
    """Split every dataset into halves A and B.

    Args:
        questions: Per dataset, the document ID of each question ID. Only
            FinanceBench reads the document ID; other datasets may give None.
        seed: Shuffle seed (20261115 registered).

    Returns:
        Per dataset, the half of each question ID.
    """
    halves: Halves = {}
    for dataset in sorted(questions):
        rows = questions[dataset]
        if dataset == DOCUMENT_SPLIT:
            halves[dataset] = split_by_document({q: str(doc) for q, doc in rows.items()}, seed)
        else:
            halves[dataset] = split_by_question(list(rows), seed)
    return halves


def write_halves(halves: Halves, path: Path, seed: int = SEED) -> str:
    """Write ``halves.json`` atomically and return its SHA-256.

    Args:
        halves: Output of ``make_halves``.
        path: Target file.
        seed: Seed recorded in the file.

    Returns:
        The SHA-256 of the written bytes.
    """
    body = json.dumps({"seed": seed, "halves": halves}, sort_keys=True, indent=2) + "\n"
    data = body.encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return hashlib.sha256(data).hexdigest()


def read_halves(path: Path) -> Halves:
    """Read the halves of ``halves.json``.

    Args:
        path: The file.

    Returns:
        Per dataset, the half of each question ID.
    """
    return json.loads(path.read_text(encoding="utf-8"))["halves"]


def ids_in_half(halves: Halves, dataset: str, half: str) -> frozenset[str]:
    """Return the question IDs of one dataset in one half.

    Args:
        halves: Per dataset, the half of each question ID.
        dataset: Dataset name.
        half: ``A`` or ``B``.

    Returns:
        The question IDs.
    """
    if half not in HALVES:
        raise ValueError(f"half must be A or B, got {half!r}")
    return frozenset(qid for qid, h in halves[dataset].items() if h == half)
