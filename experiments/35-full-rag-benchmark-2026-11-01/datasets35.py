"""Experiment 35 datasets: questions, gold labels, frozen order and corpus files (design D29).

The data stays outside git, under the folder ``EXP35_DATA_DIR`` names
(default ``~/Development/DATA/omrs``), in the layout protocol section 4.1
records:

* FinanceBench: ``benchmarks/financebench/financebench_merged.jsonl`` and
  ``pdfs/<doc_name>.pdf``. Gold is the evidence document and page, converted
  to the OMRS page label by ``gold_rules.financebench_page_label``.
* FreshStack: Experiment 22's ``ground-truth.json``, without the 20
  continuity queries (203 remain). The corpus is the full public
  ``freshstack/corpus-oct-2024`` config ``langchain`` (parquet files under
  ``benchmarks/freshstack/corpus-oct-2024/langchain/`` and a ``download.json``
  that names the downloaded revision), checked against ``plan.json``
  ``pins.datasets.freshstack``. The query is the title, a blank line, then the
  body. Gold is the corpus IDs.
* BioASQ: the ``test`` parquet files of ``enelpol/rag-mini-bioasq``. Gold is
  the passage IDs.
* Legal RAG Bench: the ``qa`` and ``corpus`` configs of
  ``isaacus/legal-rag-bench``, split ``test`` (100 questions). Gold is
  ``relevant_passage_id``. Input hashes come from ``plan.json``
  ``pins.datasets.legal.sha256``.

FreshStack, BioASQ and Legal are indexed from passage files that
``prepare35.py`` writes once into a fixed folder outside the output folder
(``--passages-dir``, task 5.4c), with a tree hash. A loader refuses a question
with no gold unit and names it. The question order is frozen: sort by ID,
then shuffle with the plan seed.
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

import arms
from experiments._lib.gold_rules import financebench_page_label

DATA_DIR_ENV = "EXP35_DATA_DIR"
DEFAULT_DATA_DIR = "~/Development/DATA/omrs"
DATASETS = ("financebench", "freshstack", "bioasq", "legal")
#: Datasets indexed from prepared passage files (``prepare35.py``).
PASSAGE_DATASETS = ("freshstack", "bioasq", "legal")
TREE_FILE = "passages-tree.json"
MANIFEST_FILE = "manifest.jsonl"
LEGAL_ROWS = 100

_FB = "benchmarks/financebench"
_FS_GT = "experiments/22-raw-query-qwen4b-baseline-2026-09-07/ground-truth.json"
_FS_CORPUS = "benchmarks/freshstack/corpus-oct-2024/langchain"
_BIO_Q = "benchmarks/bioasq/question-answer-passages/test-00000-of-00001.parquet"
_BIO_C = "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet"
_LEGAL_Q = "benchmarks/legal-rag-bench/qa/test-00000-of-00001.parquet"
_LEGAL_C = "benchmarks/legal-rag-bench/corpus/test-00000-of-00001.parquet"

#: Recorded SHA-256 of each input file (protocol section 4.1, step 6.1). Legal
#: and the FreshStack corpus are pinned in ``plan.json`` (P1, task 13.4).
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
    },
    "bioasq": {
        _BIO_Q: "af1e6bb5e191821e7edfed4118658551612c33759ee25fb601647cda0e0ff602",
        _BIO_C: "8ac2d54f2fe5de176f452eb88987b0452c79b60b818769dab2c38f313f72d211",
    },
}


class DatasetError(RuntimeError):
    """A dataset input is missing, changed or does not match its pin."""


@dataclass(frozen=True)
class Question:
    """One benchmark question.

    Attributes:
        qid: The question ID as text.
        text: The question sent to search and answer.
        relevant: Gold unit IDs.
        reference: The reference answer, or ``""``.
        gold_pages: FinanceBench only: gold document to OMRS page labels.
    """

    qid: str
    text: str
    relevant: tuple[str, ...]
    reference: str = ""
    gold_pages: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def data_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the absolute data folder.

    Raises:
        DatasetError: The folder does not exist; names the variable.
    """
    env = os.environ if environ is None else environ
    folder = Path(env.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR).expanduser().resolve()
    if not folder.is_dir():
        raise DatasetError(f"{DATA_DIR_ENV} names {folder}, not an existing folder")
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
        DatasetError: Names the file and both hashes.
    """
    for relpath, want in expected.items():
        path = root / relpath
        if not path.is_file():
            raise DatasetError(f"input {relpath} is missing under {root}")
        found = file_sha256(path)
        if found != want:
            raise DatasetError(f"input {relpath} has SHA-256 {found}; the record is {want}")


def _pin(plan: Mapping[str, Any], dataset: str, key: str) -> Any:
    return arms.pinned(plan, "pins", "datasets", dataset, key, error=DatasetError)


def input_hashes(dataset: str, plan: Mapping[str, Any]) -> dict[str, str]:
    """Return the recorded input hashes of *dataset* (Legal from ``plan.json``).

    Raises:
        DatasetError: Legal has no ``pins.datasets.legal.sha256`` in the plan.
    """
    if dataset == "legal":
        return dict(_pin(plan, "legal", "sha256"))
    return dict(EXPECTED_SHA256[dataset])


def freshstack_pin(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``plan.json`` ``pins.datasets.freshstack``: ``revision`` and ``rows``.

    Raises:
        DatasetError: The plan records no revision or row count (P1).
    """
    return {key: _pin(plan, "freshstack", key) for key in ("revision", "rows")}


def check_passages(passages_dir: Path, dataset: str, plan: Mapping[str, Any]) -> Path:
    """Verify a prepared passage folder against its record and ``plan.json``; return it.

    The plan pin is ``pins.datasets.<dataset>.passages_tree_sha256``, recorded
    when ``prepare35.py`` ran (task 5.4c).

    Raises:
        DatasetError: A file differs from the folder's record (named), or the
            tree hash differs from the plan, or the plan has no pin.
    """
    folder = passages_dir / dataset
    found = verify_tree(folder)
    pinned = _pin(plan, dataset, "passages_tree_sha256")
    if found != pinned:
        raise DatasetError(f"passage folder {folder} has tree hash {found}; the plan pins {pinned}")
    return folder


def pdf_hashes(root: Path, files: Sequence[Path]) -> dict[str, str]:
    """Return the recorded SHA-256 of each FinanceBench PDF in *files* (``PDFS_MANIFEST.json``)."""
    manifest = json.loads((root / _FB / "PDFS_MANIFEST.json").read_text(encoding="utf-8"))
    return {f"{_FB}/pdfs/{path.name}": manifest["files"][path.stem]["sha256"] for path in files}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _parquet_rows(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


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
            text=f"{q['query_title']}\n\n{q['query_text']}",
            relevant=tuple(str(p) for p in q["relevant_parent_ids"]),
            reference=str(q.get("answer_text") or ""),
        )
        for q in queries
        if not str(q["query_id"]).startswith("continuity")
    ]


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


def _legal(root: Path) -> list[Question]:
    rows = _parquet_rows(root / _LEGAL_Q)
    if len(rows) != LEGAL_ROWS:
        raise DatasetError(f"Legal RAG Bench qa holds {len(rows)} rows; the plan has {LEGAL_ROWS}")
    passages = set(legal_passages(root))
    missing = sorted({str(r["relevant_passage_id"]) for r in rows} - passages)
    if missing:
        raise DatasetError(f"Legal RAG Bench gold passage {missing[0]} is not in the corpus")
    return [
        Question(
            qid=str(row["id"]),
            text=str(row["question"]),
            relevant=(str(row["relevant_passage_id"]),),
            reference=str(row.get("answer") or ""),
        )
        for row in rows
    ]


def legal_passages(root: Path) -> dict[str, dict[str, str]]:
    """Return the Legal RAG Bench passages by ID: ``title``, ``text`` and ``footnotes``."""
    return {
        str(r["id"]): {k: str(r.get(k) or "") for k in ("title", "text", "footnotes")}
        for r in _parquet_rows(root / _LEGAL_C)
    }


def bioasq_passages(root: Path) -> dict[str, str]:
    """Return the BioASQ passages by ID."""
    return {str(r["id"]): str(r["passage"]) for r in _parquet_rows(root / _BIO_C)}


def freshstack_corpus(root: Path, pin: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return the FreshStack corpus rows ``(id, text)`` in file order, checked against *pin*.

    Args:
        root: The data folder.
        pin: ``plan.json`` ``pins.datasets.freshstack``: ``revision`` and ``rows``.

    Raises:
        DatasetError: The downloaded revision or the row count differs from
            the pin; the message names the field.
    """
    folder = root / _FS_CORPUS
    found = json.loads((folder / "download.json").read_text(encoding="utf-8")).get("revision")
    if found != pin["revision"]:
        raise DatasetError(
            f"FreshStack corpus revision is {found}; the plan pins {pin['revision']}"
        )
    rows = [row for path in sorted(folder.glob("*.parquet")) for row in _parquet_rows(path)]
    if len(rows) != int(pin["rows"]):
        raise DatasetError(f"FreshStack corpus has {len(rows)} rows; the plan pins {pin['rows']}")
    return [(str(r["_id"]), str(r["text"])) for r in rows]


def load_questions(dataset: str, root: Path) -> list[Question]:
    """Return every question of *dataset*, in file order.

    Raises:
        DatasetError: A question has no gold unit (named), or a Legal input
            does not match the plan shape.
    """
    loaders = {
        "financebench": _financebench,
        "freshstack": _freshstack,
        "bioasq": _bioasq,
        "legal": _legal,
    }
    questions = loaders[dataset](root)
    empty = [q.qid for q in questions if not q.relevant]
    if empty:
        raise DatasetError(f"{dataset} question {empty[0]} has no gold unit")
    return questions


def frozen_order(questions: Sequence[Question], *, seed: int) -> list[Question]:
    """Return the questions sorted by ID, then shuffled with *seed*."""
    ordered = sorted(questions, key=lambda q: q.qid)
    random.Random(seed).shuffle(ordered)  # noqa: S311 - a fixed order, not security
    return ordered


def select(
    questions: Sequence[Question],
    limit: int | None,
    *,
    seed: int,
    qids: Sequence[str] | None = None,
) -> list[Question]:
    """Return the selected questions in frozen order.

    Args:
        questions: Every question of the dataset.
        limit: Keep the first *limit* questions, or all when ``None``.
        seed: The question-order seed.
        qids: Keep only these question IDs (``--qids``), still in frozen order.

    Raises:
        DatasetError: A named ID is not in the dataset; the message names it.
    """
    ordered = frozen_order(questions, seed=seed)
    if qids:
        unknown = sorted(set(qids) - {q.qid for q in ordered})
        if unknown:
            raise DatasetError(f"--qids names unknown question {', '.join(unknown)}")
        ordered = [q for q in ordered if q.qid in set(qids)]
    return ordered if limit is None else ordered[:limit]


def tree_hash(files: Mapping[str, str]) -> str:
    """Return the SHA-256 of the canonical JSON of a ``{file name: SHA-256}`` map."""
    text = json.dumps(dict(sorted(files.items())), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_tree(folder: Path) -> str:
    """Check every file of a prepared passage folder against ``passages-tree.json``.

    Returns:
        The recorded tree hash.

    Raises:
        DatasetError: The record is missing, or a file is missing, added or
            changed; the message names the first such file.
    """
    record_path = folder / TREE_FILE
    if not record_path.is_file():
        raise DatasetError(f"{folder} has no {TREE_FILE}; run prepare35.py first")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    present = {p.name for p in folder.iterdir() if p.is_file() and p.name != TREE_FILE}
    for name in sorted(present ^ set(record["files"])):
        raise DatasetError(f"passage folder {folder}: {name} is added or missing")
    for name in sorted(present):
        if file_sha256(folder / name) != record["files"][name]:
            raise DatasetError(f"passage folder {folder}: {name} differs from {TREE_FILE}")
    if tree_hash(record["files"]) != record["tree_sha256"]:
        raise DatasetError(f"{record_path} tree_sha256 does not match its file list")
    return str(record["tree_sha256"])


def freshstack_unit_map(folder: Path) -> dict[str, str]:
    """Return FreshStack file stem to corpus ID, from the prepared ``manifest.jsonl``."""
    return {
        Path(row["file"]).stem: str(row["freshstack_id"]) for row in _jsonl(folder / MANIFEST_FILE)
    }


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
    passages_dir: Path,
    *,
    seed: int,
) -> list[Path]:
    """Return the files to ingest, in name order.

    Args:
        dataset: The dataset name.
        root: The data folder (FinanceBench PDFs).
        questions: The selected questions (their gold documents are always kept).
        corpus_sample: ``None`` for the full corpus, or the number of
            non-gold documents to add, sampled with *seed* (smoke runs).
        passages_dir: The prepared passage folder (``--passages-dir``); the
            files of a passage dataset sit in ``<passages_dir>/<dataset>``.
        seed: The sample seed (``plan.json`` ``seeds.smoke_sample``).

    Raises:
        DatasetError: A passage dataset has no prepared folder, or a gold
            document is missing.
    """
    if dataset == "financebench":
        manifest = json.loads((root / _FB / "PDFS_MANIFEST.json").read_text(encoding="utf-8"))
        gold = {doc for q in questions for doc in q.gold_pages}
        docs = _sample(sorted(manifest["files"]), gold, corpus_sample, seed)
        return [root / _FB / "pdfs" / f"{doc}.pdf" for doc in docs]
    folder = passages_dir / dataset
    if not (folder / TREE_FILE).is_file():
        raise DatasetError(
            f"{folder} holds no prepared passages; run prepare35.py --dataset "
            f"{dataset} --passages-dir {passages_dir} first"
        )
    stems = sorted(p.stem for p in folder.glob("*.md"))
    to_unit = freshstack_unit_map(folder) if dataset == "freshstack" else {s: s for s in stems}
    gold_units = {u for q in questions for u in q.relevant}
    gold = {s for s in stems if to_unit.get(s) in gold_units}
    missing = sorted(gold_units - {to_unit.get(s) for s in stems})
    if missing:
        raise DatasetError(f"{dataset} gold document {missing[0]} has no passage file in {folder}")
    return [folder / f"{s}.md" for s in _sample(stems, gold, corpus_sample, seed)]
