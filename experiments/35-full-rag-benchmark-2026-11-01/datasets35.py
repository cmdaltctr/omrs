"""Experiment 35 datasets: questions, gold labels, frozen order and corpus files (design D2).

The data stays outside git, under the folder that ``EXP35_DATA_DIR`` names
(default ``~/Development/DATA/omrs``), in the layout protocol section 4.1
records:

* FinanceBench: ``benchmarks/financebench/financebench_merged.jsonl`` and
  ``pdfs/<doc_name>.pdf``. Gold is the evidence document and page, converted
  to the OMRS page label by ``gold_rules.financebench_page_label``.
* FreshStack: Experiment 22's ``ground-truth.json`` (223 queries) and the
  ``freshstack-corpus`` export, plus the overlay runbook (the 10,025th file).
  Gold is the parent IDs; chunks map to parents through the manifest.
* BioASQ: the ``test`` parquet files of ``enelpol/rag-mini-bioasq``. Each
  passage is written once as ``<id>.txt`` in the work folder, so the file name
  carries the passage ID.

Question order is frozen: sort by question ID, then shuffle with the plan seed.
``--limit N`` takes the first N of that order, so a smoke run is the head of
the main run.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from experiments._lib.gold_rules import financebench_page_label

DATA_DIR_ENV = "EXP35_DATA_DIR"
DEFAULT_DATA_DIR = "~/Development/DATA/omrs"
DATASETS = ("financebench", "freshstack", "bioasq")

_FB = "benchmarks/financebench"
_FS_GT = "experiments/22-raw-query-qwen4b-baseline-2026-09-07/ground-truth.json"
_FS_CORPUS = "experiments/freshstack-corpus"
_FS_OVERLAY = "benchmarks/freshstack/overlay/zzqj-9097-runbook.md"
_FS_OVERLAY_ID = "continuity/zzqj-9097-runbook.md"
_BIO_Q = "benchmarks/bioasq/question-answer-passages/test-00000-of-00001.parquet"
_BIO_C = "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet"

#: Recorded SHA-256 of each input file (protocol section 4.1, step 6.1).
EXPECTED_SHA256: Mapping[str, Mapping[str, str]] = {
    "financebench": {
        f"{_FB}/financebench_merged.jsonl": (
            "7a1c81789e0fd2f1c37057a7ec0097756d726b05e7228e68e57db8e18c54fd0b"
        ),
        f"{_FB}/PDFS_MANIFEST.json": (
            "871478cee4d9ee5001b33e4a981015a95c0cca780f5d75051123685886e5c74d"
        ),
    },
    "freshstack": {
        _FS_GT: "3860314c74a5c0be4d10f7cdd4d9d55d1daea4cfedf9dcd60d8fbe20d43b4fe8",
        f"{_FS_CORPUS}/langchain_manifest.jsonl": (
            "f1e97574229ba474e5b77a338eecbb3c756071f630c312757e0d0aebc702e20e"
        ),
        _FS_OVERLAY: "0473106c84f1f7bf1750e6ed03d294cf77c0464347104f64a8b93cf8afa87e0f",
    },
    "bioasq": {
        _BIO_Q: "af1e6bb5e191821e7edfed4118658551612c33759ee25fb601647cda0e0ff602",
        _BIO_C: "8ac2d54f2fe5de176f452eb88987b0452c79b60b818769dab2c38f313f72d211",
    },
}


class DatasetError(RuntimeError):
    """A dataset input is missing or differs from the record."""


@dataclass(frozen=True)
class Question:
    """One benchmark question.

    Attributes:
        qid: The question ID as text.
        text: The question sent to search and answer.
        relevant: Gold unit IDs for Recall@10, MRR@10 and nDCG@10.
        reference: The reference answer, or ``""``.
        gold_pages: FinanceBench only: gold document to its OMRS page labels.
    """

    qid: str
    text: str
    relevant: tuple[str, ...]
    reference: str = ""
    gold_pages: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def data_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the absolute data folder.

    Raises:
        DatasetError: The folder does not exist; the message names the variable.
    """
    env = os.environ if environ is None else environ
    folder = Path(env.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR).expanduser().resolve()
    if not folder.is_dir():
        raise DatasetError(f"{DATA_DIR_ENV} names {folder}, which is not an existing folder")
    return folder


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_inputs(root: Path, expected: Mapping[str, str]) -> None:
    """Stop when an input file is missing or its SHA-256 differs from the record.

    Raises:
        DatasetError: The message names the file and both hashes.
    """
    for relpath, want in expected.items():
        path = root / relpath
        if not path.is_file():
            raise DatasetError(f"input {relpath} is missing under {root}")
        found = file_sha256(path)
        if found != want:
            raise DatasetError(f"input {relpath} has SHA-256 {found}; the record is {want}")


def pdf_hashes(root: Path, files: Sequence[Path]) -> dict[str, str]:
    """Return the recorded SHA-256 of each FinanceBench PDF in *files* (``PDFS_MANIFEST.json``)."""
    manifest = json.loads((root / _FB / "PDFS_MANIFEST.json").read_text(encoding="utf-8"))
    return {f"{_FB}/pdfs/{path.name}": manifest["files"][path.stem]["sha256"] for path in files}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _financebench(root: Path) -> list[Question]:
    questions = []
    for row in _jsonl(root / _FB / "financebench_merged.jsonl"):
        pages: dict[str, list[str]] = {}
        for evidence in row["evidence"]:
            doc = evidence.get("doc_name") or row["doc_name"]
            label = financebench_page_label(int(evidence["evidence_page_num"]))
            pages.setdefault(doc, [])
            if label not in pages[doc]:
                pages[doc].append(label)
        relevant = tuple(f"{doc}#p{label}" for doc, labels in pages.items() for label in labels)
        questions.append(
            Question(
                qid=str(row["financebench_id"]),
                text=str(row["question"]),
                relevant=relevant,
                reference=str(row.get("answer") or ""),
                gold_pages={doc: tuple(labels) for doc, labels in pages.items()},
            )
        )
    return questions


def _freshstack(root: Path) -> list[Question]:
    queries = json.loads((root / _FS_GT).read_text(encoding="utf-8"))["queries"]
    return [
        Question(
            qid=str(q["query_id"]),
            text=str(q["query"]),
            relevant=tuple(str(p) for p in q["relevant_parent_ids"]),
            reference=str(q.get("answer_text") or ""),
        )
        for q in queries
    ]


def _parquet_rows(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def _bioasq(root: Path) -> list[Question]:
    return [
        Question(
            qid=str(row["id"]),
            text=str(row["question"]),
            relevant=tuple(str(p) for p in row["relevant_passage_ids"]),
            reference=str(row.get("answer") or ""),
        )
        for row in _parquet_rows(root / _BIO_Q)
    ]


def load_questions(dataset: str, root: Path) -> list[Question]:
    """Return every question of *dataset*, in file order."""
    loaders = {"financebench": _financebench, "freshstack": _freshstack, "bioasq": _bioasq}
    return loaders[dataset](root)


def frozen_order(questions: Sequence[Question], *, seed: int) -> list[Question]:
    """Return the questions sorted by ID, then shuffled with *seed*."""
    ordered = sorted(questions, key=lambda q: q.qid)
    random.Random(seed).shuffle(ordered)  # noqa: S311 - a fixed order, not security
    return ordered


def select(questions: Sequence[Question], limit: int | None, *, seed: int) -> list[Question]:
    """Return the first *limit* questions of the frozen order (all when ``None``)."""
    ordered = frozen_order(questions, seed=seed)
    return ordered if limit is None else ordered[:limit]


def freshstack_id_map(root: Path) -> dict[str, str]:
    """Return FreshStack file name to parent ID, with the overlay runbook added."""
    mapping = {
        str(row["metadata"]["file_name"]): str(row["freshstack_id"])
        for row in _jsonl(root / _FS_CORPUS / "langchain_manifest.jsonl")
    }
    mapping[Path(_FS_OVERLAY).name] = _FS_OVERLAY_ID
    return mapping


def _sample(keys: Sequence[str], gold: set[str], corpus_sample: int | None, seed: int) -> list[str]:
    """Return every key when *corpus_sample* is ``None``, else gold plus a seeded sample."""
    if corpus_sample is None:
        return list(keys)
    others = sorted(k for k in keys if k not in gold)
    picked = set(random.Random(seed).sample(others, min(corpus_sample, len(others))))  # noqa: S311
    return [k for k in keys if k in gold or k in picked]


def corpus_files(
    dataset: str,
    root: Path,
    questions: Sequence[Question],
    corpus_sample: int | None,
    work_dir: Path,
    *,
    seed: int = 20261101,
) -> list[Path]:
    """Return the files to ingest, in a fixed order.

    Args:
        dataset: The dataset name.
        root: The data folder.
        questions: The selected questions (their gold documents are always kept).
        corpus_sample: ``None`` for the full corpus, else the number of
            non-gold documents to add, sampled with *seed*.
        work_dir: Where BioASQ passages are written as files.
        seed: The sample seed.
    """
    if dataset == "financebench":
        manifest = json.loads((root / _FB / "PDFS_MANIFEST.json").read_text(encoding="utf-8"))
        gold = {doc for q in questions for doc in q.gold_pages}
        docs = _sample(sorted(manifest["files"]), gold, corpus_sample, seed)
        return [root / _FB / "pdfs" / f"{doc}.pdf" for doc in docs]
    if dataset == "freshstack":
        id_map = freshstack_id_map(root)
        corpus = root / _FS_CORPUS
        files = sorted(corpus.glob("langchain/*.md")) + sorted(corpus.glob("continuity/*.md"))
        files.append(root / _FS_OVERLAY)
        gold = {p for q in questions for p in q.relevant}
        names = [f.name for f in files if id_map.get(f.name) in gold]
        keep = set(_sample([f.name for f in files], set(names), corpus_sample, seed))
        kept = [f for f in files if f.name in keep]
        missing = sorted(gold - {id_map.get(f.name) for f in kept})
        if missing:
            raise DatasetError(
                f"{len(missing)} FreshStack gold documents are missing under {corpus} "
                f"(first: {missing[0]}); copy the whole freshstack-corpus folder, not "
                "only its manifest"
            )
        return kept
    return _bioasq_files(root, questions, corpus_sample, work_dir, seed)


def _bioasq_files(
    root: Path,
    questions: Sequence[Question],
    corpus_sample: int | None,
    work_dir: Path,
    seed: int,
) -> list[Path]:
    rows = {str(r["id"]): str(r["passage"]) for r in _parquet_rows(root / _BIO_C)}
    gold = {p for q in questions for p in q.relevant if p in rows}
    ids = _sample(sorted(rows, key=int), gold, corpus_sample, seed)
    folder = work_dir / "bioasq-corpus"
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for passage_id in ids:
        path = folder / f"{passage_id}.txt"
        if not path.is_file():
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(rows[passage_id], encoding="utf-8")
            tmp.replace(path)
        files.append(path)
    return files
