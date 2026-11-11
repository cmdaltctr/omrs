"""Pure helpers for the 20-answer measurement (Experiment 35 pre-freeze, master task 6.3).

Nothing here imports OMRS, the router, the network or Ragas, so the tests run
on stubs. Rows hold ids and numbers only: never question, answer, context or
reference text.
"""

from __future__ import annotations

import json
import math
import os
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

#: One seed for the question sample, the answer model and the judge (brief, 2026-11-09).
SEED = 20261109
DEFAULT_LIMIT = 20
ANSWER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_REASONING = "low"
TEMPERATURE = 0.0

# Main Experiment 35a run (design D1 to D3, protocol section 4). Change the sizes here only.
#: Arms in the main run.
MAIN_ARMS = 6
#: Questions per arm and run: FinanceBench 150 + FreshStack 223 + BioASQ 707.
MAIN_QUESTIONS = 150 + 223 + 707
#: Repeat runs of every arm.
MAIN_RUNS = 3
#: Questions with a reference answer (FinanceBench + BioASQ). Context precision and
#: context recall need one, so FreshStack does not take them (design D4).
MAIN_REFERENCE_QUESTIONS = 150 + 707

METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
REFERENCE_METRICS = ("context_precision", "context_recall")
_ERROR_CAP = 300


class StageFileExistsError(RuntimeError):
    """A stage file holds rows and ``--resume`` is not set."""


# --- questions ------------------------------------------------------------------


def question_pool(exp2: Sequence[Mapping], financebench: Sequence[Mapping]) -> list[dict]:
    """Return the Part A questions with stable ids. Text stays in memory only.

    Experiment 2 rows carry no id, so the id is the file position (``exp2-00``).
    FinanceBench rows keep their ``financebench_id``.
    """
    pool = [
        {
            "qid": f"exp2-{i:02d}",
            "dataset": "exp2",
            "question": str(row["query"]),
            "reference": str(row.get("expected_answer") or ""),
        }
        for i, row in enumerate(exp2)
    ]
    pool += [
        {
            "qid": str(row["financebench_id"]),
            "dataset": "financebench",
            "question": str(row["question"]),
            "reference": str(row.get("answer") or ""),
        }
        for row in financebench
    ]
    return pool


def sample_questions(pool: Sequence[Mapping], limit: int, seed: int = SEED) -> list[dict]:
    """Return *limit* questions: a seeded order of the pool sorted by id, then its prefix.

    A smaller limit gives a prefix of a larger one, so ``--limit`` changes keep ids.

    Raises:
        ValueError: Ids repeat, or *limit* is above the pool size.
    """
    ordered = sorted((dict(q) for q in pool), key=lambda q: q["qid"])
    if len({q["qid"] for q in ordered}) != len(ordered):
        raise ValueError("question ids repeat in the Part A pool")
    if limit > len(ordered):
        raise ValueError(f"--limit {limit} is above the {len(ordered)} Part A questions")
    rng = random.Random(seed)  # noqa: S311 - a seeded sample, not a secret
    return rng.sample(ordered, len(ordered))[:limit]


# --- files ----------------------------------------------------------------------


def read_rows(path: Path) -> list[dict]:
    """Return the JSON rows of *path*; a torn last line (a crash mid-write) is dropped."""
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
    return rows


def check_fresh(path: Path, resume: bool) -> None:
    """Refuse to add rows to a stage file from an earlier run unless resuming.

    Raises:
        StageFileExistsError: *path* holds rows and *resume* is false.
    """
    if not resume and read_rows(path):
        raise StageFileExistsError(
            f"{path} already holds rows. Pass --resume to continue it, or remove it."
        )


def append_row(path: Path, row: Mapping[str, Any]) -> None:
    """Append one row to *path* and flush it to disk.

    A torn last line (a crash mid-write) has no newline. :func:`read_rows` already
    ignores it, so it is cut off first; the new row then starts its own line and
    every later row stays readable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size:
        data = path.read_bytes()
        if not data.endswith(b"\n"):
            with path.open("r+b") as handle:
                handle.truncate(data.rfind(b"\n") + 1)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_json_atomic(path: Path, data: Any) -> None:
    """Write *data* as JSON through ``<name>.tmp`` and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write *rows* as JSON lines through ``<name>.tmp`` and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def scrub(message: str, texts: Sequence[str]) -> str:
    """Return *message* with each text of *texts* replaced, capped in length.

    Texts under 4 characters stay: replacing "r" or "No" would wreck the message
    and cannot leak a question or a claim.
    """
    for text in sorted((t for t in texts if len(t.strip()) >= 4), key=len, reverse=True):
        message = message.replace(text, "[text]")
    return message[:_ERROR_CAP]


# --- rows -----------------------------------------------------------------------


def answer_row(
    question: Mapping[str, Any],
    result: Mapping[str, Any],
    seconds: float,
    error: str,
    configured: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the ids-and-numbers row of one answer.

    Args:
        question: The sampled question (its text is only used to scrub the error).
        result: The ``Engine.answer`` result, or ``{}`` after an exception.
        seconds: Wall time of the call.
        error: The exception text, or ``""``.
        configured: ``model``, ``temperature`` and ``seed`` set in the scratch settings.
            The values the request carried (``sampling.chat``) win when present.
    """
    usage = result.get("usage") or {}
    chat = (result.get("sampling") or {}).get("chat") or {}
    text = str(result.get("answer") or "")
    if not error and result.get("status") == "error":
        error = str(result.get("error") or "answer status error")
    if not error and not result:
        error = "empty answer result"
    texts = [question.get("question", ""), question.get("reference", ""), text]
    texts += [str(e.get("text") or "") for e in result.get("evidence") or []]
    return {
        "qid": question["qid"],
        "dataset": question.get("dataset", ""),
        "status": result.get("status"),
        "answer_chars": len(text),
        "evidence": len(result.get("evidence") or []),
        "citations": len(result.get("citations") or []),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "calls": usage.get("calls", 0),
        "reported_cost_usd": usage.get("cost_usd"),
        "seconds": round(seconds, 3),
        "host": chat.get("host"),
        "host_in_list": chat.get("host_in_list"),
        "model": configured.get("model"),
        "temperature": chat.get("temperature", configured.get("temperature")),
        "seed": chat.get("seed", configured.get("seed")),
        "error": scrub(error, texts),
    }


# --- summary --------------------------------------------------------------------


def _num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        return 0.0
    return float(value)


def _mean(total: float, n: int) -> float | None:
    return round(total / n, 3) if n else None


def answer_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return per-answer and mean tokens and seconds; every row counts in the denominator."""
    n = len(rows)
    names = ("input_tokens", "output_tokens", "reasoning_tokens", "seconds")
    totals = {name: sum(_num(r.get(name)) for r in rows) for name in names}
    return {
        "n": n,
        "errors": sum(1 for r in rows if r.get("error")),
        "unreported_token_rows": sum(
            1 for r in rows if r.get("input_tokens") is None or r.get("output_tokens") is None
        ),
        "hosts": dict(Counter(str(r.get("host")) for r in rows)),
        "reported_cost_usd_total": round(sum(_num(r.get("reported_cost_usd")) for r in rows), 8),
        **{f"total_{name}": round(value, 3) for name, value in totals.items()},
        **{f"mean_{name}": _mean(value, n) for name, value in totals.items()},
        "per_answer": [
            {
                "qid": r["qid"],
                **{name: r.get(name) for name in names},
                "host": r.get("host"),
                "failed": bool(r.get("error")),
            }
            for r in rows
        ],
    }


def ragas_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return Ragas calls, tokens and seconds per metric and per answer (denominator: rows)."""
    n = len(rows)
    figures = ("calls", "input_tokens", "output_tokens", "reasoning_tokens", "seconds")
    per_metric: dict[str, Any] = {}
    for name in METRICS:
        entries = [(r.get("metrics") or {}).get(name) or {} for r in rows]
        scores = [e["score"] for e in entries if isinstance(e.get("score"), (int, float))]
        per_metric[name] = {
            **{f"mean_{f}": _mean(sum(_num(e.get(f)) for e in entries), n) for f in figures},
            "errors": sum(1 for e in entries if e.get("error")),
            "scored": len(scores),
            "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
        }
    per_answer = [
        {
            "qid": r["qid"],
            "failed": bool(r.get("error")),
            **{
                f: round(sum(_num(m.get(f)) for m in (r.get("metrics") or {}).values()), 3)
                for f in figures
            },
        }
        for r in rows
    ]
    return {
        "n": n,
        "errors": sum(1 for r in rows if r.get("error")),
        "ragas_versions": sorted(
            {str(r.get("ragas_version")) for r in rows if r.get("ragas_version")}
        ),
        "hosts": dict(Counter(str(c.get("host")) for r in rows for c in r.get("calls") or [])),
        "per_metric": per_metric,
        "per_answer": per_answer,
        **{f"mean_{f}_per_answer": _mean(sum(a[f] for a in per_answer), n) for f in figures},
    }


# --- cost -----------------------------------------------------------------------


def load_prices(path: Path) -> dict[str, dict[str, float]]:
    """Read ``prices.json``: per model id, ``prompt_per_million`` and ``completion_per_million``.

    Raises:
        ValueError: An entry lacks a field or holds a negative or non-number price.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    prices: dict[str, dict[str, float]] = {}
    for model, entry in data.items():
        prices[model] = {}
        for field in ("prompt_per_million", "completion_per_million"):
            value = entry.get(field) if isinstance(entry, dict) else None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{path}: {model} needs a non-negative number {field}")
            prices[model][field] = value
    return prices


def _price(prices: Mapping[str, Mapping[str, float]], model: str) -> Mapping[str, float]:
    if model not in prices:
        raise KeyError(f"prices.json has no entry for {model}")
    return prices[model]


def dollars(input_tokens: Any, output_tokens: Any, price: Mapping[str, float]) -> float:
    """Return the dollars of one call or row.

    OpenRouter's ``completion_tokens`` already holds the reasoning tokens (they
    are billed as output), so reasoning tokens are not added again.
    """
    return (
        _num(input_tokens) * price["prompt_per_million"]
        + _num(output_tokens) * price["completion_per_million"]
    ) / 1_000_000


def extrapolate(
    per_answer: float,
    arms: int = MAIN_ARMS,
    questions: int = MAIN_QUESTIONS,
    runs: int = MAIN_RUNS,
) -> dict[str, Any]:
    """Return the answer count and dollars of the main run at *per_answer* dollars each."""
    answers = arms * questions * runs
    return {"answers": answers, "dollars": round(per_answer * answers, 6)}


def cost_block(
    answer_rows: Sequence[Mapping[str, Any]],
    ragas_rows: Sequence[Mapping[str, Any]],
    prices: Mapping[str, Mapping[str, float]],
    answer_model: str = ANSWER_MODEL,
    judge_model: str = JUDGE_MODEL,
) -> dict[str, Any]:
    """Return dollars per answer for answering, for Ragas and in total, and the main run.

    Every row counts in its denominator, failed ones too. Reference metrics
    extrapolate over :data:`MAIN_REFERENCE_QUESTIONS`, the others over
    :data:`MAIN_QUESTIONS`.

    Raises:
        KeyError: *prices* has no entry for one of the two models.
    """
    answer_price, judge_price = _price(prices, answer_model), _price(prices, judge_model)
    n_answers, n_ragas = len(answer_rows), len(ragas_rows)
    answer_total = sum(
        dollars(r.get("input_tokens"), r.get("output_tokens"), answer_price) for r in answer_rows
    )
    per_metric = {}
    for name in METRICS:
        entries = [(r.get("metrics") or {}).get(name) or {} for r in ragas_rows]
        total = sum(
            dollars(e.get("input_tokens"), e.get("output_tokens"), judge_price) for e in entries
        )
        per_metric[name] = total / n_ragas if n_ragas else 0.0
    answer_per = answer_total / n_answers if n_answers else 0.0
    ragas_per = sum(per_metric.values())
    free = sum(v for k, v in per_metric.items() if k not in REFERENCE_METRICS)
    with_ref = sum(v for k, v in per_metric.items() if k in REFERENCE_METRICS)
    main = {
        "answering": extrapolate(answer_per),
        "ragas_reference_free": extrapolate(free),
        "ragas_reference": extrapolate(with_ref, questions=MAIN_REFERENCE_QUESTIONS),
    }
    main["total_dollars"] = round(sum(part["dollars"] for part in main.values()), 6)
    return {
        "prices": {answer_model: dict(answer_price), judge_model: dict(judge_price)},
        "answer_per_answer_usd": answer_per,
        "ragas_per_metric_usd": per_metric,
        "ragas_per_answer_usd": ragas_per,
        "total_per_answer_usd": answer_per + ragas_per,
        "unpriced_answer_rows": sum(
            1
            for r in answer_rows
            if r.get("input_tokens") is None or r.get("output_tokens") is None
        ),
        "unpriced_ragas_calls": sum(
            _num((m or {}).get("unreported_calls"))
            for r in ragas_rows
            for m in (r.get("metrics") or {}).values()
        ),
        "main_run": main,
        "main_run_constants": {
            "arms": MAIN_ARMS,
            "questions": MAIN_QUESTIONS,
            "reference_questions": MAIN_REFERENCE_QUESTIONS,
            "runs": MAIN_RUNS,
        },
    }
