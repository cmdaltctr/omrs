"""Experiment 35 unit scorer, token cut and FinanceBench number match.

Pre-registration sections 3 and 6 (amendment A5). The scorer reads saved
files only: per question, the ranked list of up to 100 stored chunks that the
search stage saved (chunk ID, file stem, page label), and the gold labels. It
makes no call and imports no stage code.

Unit scoring:

* Each stored chunk maps to one unit: FinanceBench ``<stem>#p<page_label>``,
  FreshStack the parent ID of its file stem, BioASQ and Legal the file stem
  (the passage ID).
* A chunk with no unit (no page label, or no parent) maps to its own
  placeholder unit. It keeps its rank, is never relevant and is counted.
* Fixed rules: the saved list order is the rank (scores are never read, so a
  tie keeps the saved order); the first occurrence of a unit keeps the unit's
  rank, and later chunks of the same unit (or the same chunk again) are
  dropped; a gold unit listed twice counts once.
* The unit list is cut at 10 units, after the collapse. Metrics follow the
  trec_eval convention: nDCG@10 (ideal DCG over min(R_q, 10) gold units),
  Recall@10, MRR@10, hit@page on FinanceBench, and ``evidence_recall_20k``
  over the chunks the 20,480-token cut keeps (:func:`evidence_by_tokens`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from experiments._lib.ranking import result_id
from experiments._lib.retrieval_metrics import ndcg_at_k

K = 10
TOKEN_BUDGET = 20_480
PLACEHOLDER = "unmapped:"
DATASETS = ("financebench", "freshstack", "bioasq", "legal")
METRICS = ("ndcg_at_10", "recall_at_10", "mrr_at_10", "evidence_recall_20k")
HALVES = ("A", "B")


def _stem(row: Mapping[str, Any]) -> str:
    if row.get("stem"):
        return str(row["stem"])
    meta = row.get("metadata") or {}
    return Path(str(meta.get("file_name") or row.get("source") or "")).stem


def _pages(row: Mapping[str, Any]) -> list[str]:
    labels = row.get("page_labels") or [row.get("page_label")]
    return [str(label) for label in labels if label is not None]


def _refuse_merged(row: Mapping[str, Any]) -> None:
    if "chunk_ids" in row or len(_pages(row)) > 1:
        raise ValueError(f"chunk {row.get('chunk_id')!r} is a merged row; score stored chunks only")


@dataclass(frozen=True)
class Gold:
    """Gold labels of one question.

    Attributes:
        qid: Question ID.
        units: Distinct gold unit IDs (never empty).
        doc_id: FinanceBench document of the question, else ``None``.
    """

    qid: str
    units: frozenset[str]
    doc_id: str | None = None


def gold_table(dataset: str, questions: Iterable[Any]) -> dict[str, Gold]:
    """Return the gold labels per question ID, refusing a question with no gold unit.

    Args:
        dataset: Dataset name.
        questions: Objects with ``qid``, ``relevant`` and ``gold_pages``, as
            ``datasets35.Question`` holds them.

    Raises:
        ValueError: A question has no gold unit; names the question.
    """
    table: dict[str, Gold] = {}
    for q in questions:
        if not q.relevant:
            raise ValueError(f"{dataset} question {q.qid} has no gold unit")
        doc_id = sorted(q.gold_pages)[0] if dataset == "financebench" else None
        table[str(q.qid)] = Gold(str(q.qid), frozenset(str(u) for u in q.relevant), doc_id)
    return table


def _unit(dataset: str, row: Mapping[str, Any], unit_map: Mapping[str, str]) -> str | None:
    stem = _stem(row)
    if dataset == "financebench":
        pages = _pages(row)
        return f"{stem}#p{pages[0]}" if stem and pages else None
    if dataset == "freshstack":
        return unit_map.get(stem)
    return stem or None


def unit_list(
    dataset: str, chunks: Sequence[Mapping[str, Any]], unit_map: Mapping[str, str] | None = None
) -> tuple[list[str], int]:
    """Collapse ranked stored chunks to units, first occurrence kept, not cut.

    Args:
        dataset: ``financebench``, ``freshstack``, ``bioasq`` or ``legal``.
        chunks: Saved stored chunks, best first.
        unit_map: FreshStack file stem to parent ID; unused elsewhere.

    Returns:
        The distinct units in rank order, and the number of unmapped chunks.

    Raises:
        ValueError: Unknown dataset, or a merged row in the list.
    """
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset!r}; expected one of {DATASETS}")
    units: list[str] = []
    unmapped = 0
    for row in chunks:
        _refuse_merged(row)
        unit = _unit(dataset, row, unit_map or {})
        if unit is None:
            unmapped += 1
            unit = PLACEHOLDER + result_id(row)
        if unit not in units:
            units.append(unit)
    return units, unmapped


def score_question(
    dataset: str,
    setup: str,
    gold: Gold,
    chunks: Sequence[Mapping[str, Any]],
    *,
    evidence_k: int,
    unit_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Score one question's saved ranked list of stored chunks.

    Args:
        dataset: Dataset name.
        setup: Search setup name, copied into the record.
        gold: The question's gold labels.
        chunks: Saved stored chunks, best first (up to 100).
        evidence_k: Number of head chunks the token cut keeps
            (``len(evidence_by_tokens(...).items)``); each, whole or
            truncated, covers its one unit.
        unit_map: FreshStack file stem to parent ID.

    Returns:
        One score record (see the module docstring and the build note).
    """
    units, unmapped = unit_list(dataset, chunks, unit_map)
    top = units[:K]
    hits = [unit in gold.units for unit in top]
    first = hits.index(True) + 1 if any(hits) else None
    evidence, _ = unit_list(dataset, chunks[:evidence_k], unit_map)
    head, _ = unit_list(dataset, chunks[:K], unit_map)
    record: dict[str, Any] = {
        "dataset": dataset,
        "setup": setup,
        "qid": gold.qid,
        "doc_id": gold.doc_id,
        "units": top,
        "unmapped_chunks": unmapped,
        "evidence_chunks": min(evidence_k, len(chunks)),
        "ndcg_at_10": ndcg_at_k(top, gold.units, K),
        "recall_at_10": sum(hits) / len(gold.units),
        "mrr_at_10": 1.0 / first if first else 0.0,
        "evidence_recall_20k": len(gold.units.intersection(evidence)) / len(gold.units),
        # Not a registered metric: the gold share among the units of the first 10
        # stored chunks, the evidence of a 10-chunk answer setup (crosstable35 misses).
        "head_recall_10": len(gold.units.intersection(head)) / len(gold.units),
    }
    if dataset == "financebench":
        record["hit_at_page"] = any(hits)
    return record


def summarise(records: Sequence[Mapping[str, Any]], *, expected_n: int) -> dict[str, Any]:
    """Return the plain mean of each metric over questions, and the unmapped-chunk count.

    Args:
        records: Score records of one dataset, setup and half.
        expected_n: Frozen question count of that dataset and half.

    Raises:
        ValueError: The count differs from *expected_n* (names both), or a
            question is scored twice (names it).
    """
    qids = [r["qid"] for r in records]
    repeated = sorted({q for q in qids if qids.count(q) > 1})
    if repeated:
        raise ValueError(f"question {repeated[0]} is scored more than once")
    if len(records) != expected_n:
        raise ValueError(f"{len(records)} questions scored; the frozen count is {expected_n}")
    names = list(METRICS) + (["hit_at_page"] if any("hit_at_page" in r for r in records) else [])
    summary: dict[str, Any] = {
        "n": len(records),
        "unmapped_chunks": sum(int(r["unmapped_chunks"]) for r in records),
    }
    for name in names:
        summary[name] = sum(float(r[name]) for r in records) / len(records) if records else None
    return summary


SELECTION_FILE = "selection.json"
TIMESTAMP_FILE = "osf-timestamp.json"
#: Fields of the OSF time-stamp record (task 16.23): upload time, uploaded
#: file's SHA-256 and the configuration hash the upload holds.
TIMESTAMP_FIELDS = ("uploaded_at", "file_sha256", "configuration_hash")


class HalfBLocked(RuntimeError):
    """Half B is not open: the selection is not written or not time-stamped (section 14.2)."""


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_half_b(root: Path | None) -> None:
    """Refuse until half B is open (pre-registration section 14.2, task 16.17).

    Half B opens when ``<root>/selection.json`` exists and
    ``<root>/osf-timestamp.json`` records an upload time, a file hash and the
    configuration hash of that ``selection.json``. The replicate pods' first
    stage calls it too.

    Raises:
        HalfBLocked: A file is missing (names each), a record field is missing,
            or the time-stamp holds another configuration hash (names both).
    """
    if root is None:
        raise HalfBLocked(
            f"half B is locked: no output folder holds {SELECTION_FILE} and {TIMESTAMP_FILE}"
        )
    missing = [n for n in (SELECTION_FILE, TIMESTAMP_FILE) if not (root / n).exists()]
    if missing:
        raise HalfBLocked(
            f"half B is locked: {' and '.join(str(root / n) for n in missing)} missing; "
            "score half A, write the selection and time-stamp its hash on OSF first"
        )
    current = _read(root / SELECTION_FILE).get("configuration_hash")
    stamp = _read(root / TIMESTAMP_FILE)
    lacking = [n for n in TIMESTAMP_FIELDS if not stamp.get(n)]
    if lacking:
        raise HalfBLocked(f"half B is locked: {TIMESTAMP_FILE} lacks {', '.join(lacking)}")
    if stamp["configuration_hash"] != current:
        raise HalfBLocked(
            f"half B is locked: {SELECTION_FILE} holds configuration hash {current}, but "
            f"{TIMESTAMP_FILE} time-stamps {stamp['configuration_hash']} (an earlier selection)"
        )


def write_scores(
    path: Path,
    content: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    half: str,
    root: Path | None = None,
) -> None:
    """Write scores atomically: a list as JSON lines, a mapping as one JSON file.

    Every score write goes through this function. A half-B write first passes
    :func:`require_half_b` on *root* (the output folder that holds
    ``selection.json``); half A needs neither file.

    Raises:
        ValueError: *half* is not ``A`` or ``B``.
        HalfBLocked: A half-B write before half B is open; nothing is written.
    """
    if half not in HALVES:
        raise ValueError(f"half must be one of {HALVES}, got {half!r}")
    if half == "B":
        require_half_b(root)
    if isinstance(content, Mapping):
        text = json.dumps(content, sort_keys=True, indent=2) + "\n"
    else:
        text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in content)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --- equal evidence by real tokens (task 15.14) -------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """One kept stored chunk of the token cut."""

    chunk_id: str
    text: str
    tokens: int
    truncated: bool


@dataclass(frozen=True)
class EvidenceCut:
    """The token cut of one question and setup.

    Attributes:
        items: Kept stored chunks in rank order; only the last can be truncated.
        cut_total: Token total of the kept chunks, before any assembly.
        truncated_chunk_id: ID of the truncated crossing chunk, else ``None``.
    """

    items: tuple[EvidenceItem, ...]
    cut_total: int
    truncated_chunk_id: str | None


def evidence_by_tokens(
    chunks: Sequence[Mapping[str, Any]],
    count_tokens: Callable[[str], int],
    truncate: Callable[[str, int], str],
    budget: int = TOKEN_BUDGET,
) -> EvidenceCut:
    """Cut stored chunks in rank order at *budget* real tokens.

    A chunk is taken while the token total before it is below *budget*. The
    chunk that crosses the limit is truncated to the tokens left and nothing
    after it is taken. A list under the budget is kept whole.

    Args:
        chunks: Stored chunks, best first, each with ``chunk_id`` and ``text``.
        count_tokens: The pinned Qwen3 token counter.
        truncate: Returns the first *n* tokens of a text.
        budget: Token limit.

    Raises:
        ValueError: A merged row in the list.
    """
    items: list[EvidenceItem] = []
    total = 0
    for row in chunks:
        if total >= budget:
            break
        _refuse_merged(row)
        text = str(row["text"])
        tokens = count_tokens(text)
        cut = total + tokens > budget
        if cut:
            text = truncate(text, budget - total)
            tokens = count_tokens(text)
        items.append(EvidenceItem(result_id(row), text, tokens, cut))
        total += tokens
    last = items[-1] if items and items[-1].truncated else None
    return EvidenceCut(tuple(items), total, last.chunk_id if last else None)


# --- FinanceBench number match (task 13.6, protocol section 0.6) --------------------------

_SCALES = {
    "thousand": 3, "k": 3, "million": 6, "mn": 6, "m": 6,
    "billion": 9, "bn": 9, "b": 9, "trillion": 12,
}  # fmt: skip
_NUMBER = re.compile(
    r"(?<![\w.,])(?P<open>\()?\$?(?P<sign>[-−])?\$?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?:%|percent\b|per cent\b)|\s?(?P<scale>"
    + "|".join(sorted(_SCALES, key=len, reverse=True))
    + r")s?\b)?(?P<close>\))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Number:
    """One number read from text: value with scale and sign, plus its written form."""

    value: Decimal
    scale: Decimal
    decimals: int


def extract_numbers(text: str) -> list[Number]:
    """Return the numbers in *text*, with thousands separators, scale words and signs read.

    Parentheses round a number, or a leading minus, make it negative. ``%``
    and ``percent`` are dropped, so ``12.5%`` reads as 12.5.
    """
    numbers = []
    for match in _NUMBER.finditer(text):
        written = match["num"].replace(",", "")
        scale = Decimal(10) ** _SCALES[match["scale"].lower()] if match["scale"] else Decimal(1)
        negative = bool(match["sign"]) or bool(match["open"] and match["close"])
        value = Decimal(written) * scale * (-1 if negative else 1)
        decimals = len(written.partition(".")[2])
        numbers.append(Number(value, scale, decimals))
    return numbers


def _same(reference: Number, answer: Number) -> bool:
    step = Decimal(1).scaleb(-reference.decimals)
    rounded = (answer.value / reference.scale).quantize(step, rounding=ROUND_HALF_UP)
    if rounded == reference.value / reference.scale:
        return True
    return abs(answer.value - reference.value) <= Decimal("0.01") * abs(reference.value)


def number_match(reference: str, answer: str) -> bool | None:
    """Return whether every reference number appears in the answer.

    A reference number matches an answer number equal to it after rounding to
    the reference's decimal places (in the reference's scale), or within 1%
    relative difference.

    Returns:
        ``True`` or ``False``; ``None`` when the reference holds no number.
    """
    wanted = extract_numbers(reference)
    if not wanted:
        return None
    found = extract_numbers(answer)
    return all(any(_same(ref, ans) for ans in found) for ref in wanted)
