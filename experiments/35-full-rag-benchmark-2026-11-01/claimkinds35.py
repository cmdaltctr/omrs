"""Claim alignment and the claim classifier for Experiment 35 (tasks 8.2 and 8.5).

Claims are split again from the saved answer with OMRS's own ``split_claims``
(the splitter the judges used) and matched to the judge verdicts by index.
A count or order mismatch stops the step and names the place.

The classifier sorts each claim into ``factual``, ``refusal`` or ``mixed``
with a fixed prompt (design D13, D14). The model sees the question and the
claim only. The model call is an injected async callable, so the caller wires
the hosted gate (``experiments/_lib/hosted_calls.py``) and its rate-limit
stop. A reply that is not one of the three kinds is saved as ``unreadable``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from outputs35 import read_rows, write_json

from omrs.core.answer.verify import split_claims

KINDS = ("factual", "refusal", "mixed")
UNREADABLE = "unreadable"
#: Exit code of a stage stopped by the rate-limit gate (design D2).
EXIT_RATE_LIMIT = 5
STAGE = "claimkinds"

#: A model call: takes chat messages, returns the reply text.
ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]

PROMPT = """You sort one sentence from an answer into one of three kinds.

factual: the sentence states a checkable fact. A negative finding that answers the question
(for example "no debt securities are listed") is factual.
refusal: the sentence only says that the sources do not cover something, or that the question
cannot be answered from them.
mixed: the sentence states a checkable fact and also a limit of what the sources cover.

You see the question and the sentence only. Reply with one word: factual, refusal or mixed.

Examples:
{examples}"""


class AlignmentError(RuntimeError):
    """Claims split from an answer do not match the judge row's verdicts."""


def claim_key(qid: str, claim: str) -> str:
    """Return the SHA-256 of the question ID and the claim text (the claim's key)."""
    return hashlib.sha256(json.dumps([qid, claim]).encode("utf-8")).hexdigest()


def answer_claims(answer: Mapping[str, Any]) -> list[str]:
    """Return the claim texts of one answer row, in answer order (none for a missing answer)."""
    text = answer.get("answer")
    if not text:
        return []
    return [claim for claim, _ in split_claims(text, len(answer.get("evidence") or []))]


def align(
    answer: Mapping[str, Any], judge: Mapping[str, Any], *, where: str
) -> list[tuple[str, dict[str, Any]]]:
    """Pair each claim of *answer* with its verdict in *judge*.

    Args:
        answer: One saved answer row.
        judge: The judge row of the same question.
        where: Dataset, setup, run and question, named in an error.

    Returns:
        ``(claim, verdict)`` pairs in answer order.

    Raises:
        AlignmentError: The counts differ, or the verdict indexes are not
            0, 1, 2 ... in order.
    """
    claims = answer_claims(answer)
    verdicts = list(judge.get("verdicts") or [])
    if len(claims) != len(verdicts):
        raise AlignmentError(f"{where}: {len(claims)} claims but {len(verdicts)} verdicts")
    if [v.get("index") for v in verdicts] != list(range(len(verdicts))):
        raise AlignmentError(f"{where}: verdicts out of order")
    return list(zip(claims, verdicts, strict=True))


def build_prompt(examples: Sequence[Mapping[str, str]]) -> str:
    """Return the fixed prompt with its examples (question, claim and kind each)."""
    lines = [
        f"Question: {e['question']}\nSentence: {e['claim']}\nKind: {e['kind']}\n" for e in examples
    ]
    return PROMPT.format(examples="\n".join(lines))


def check_examples(examples: Sequence[Mapping[str, str]], sample_keys: set[str]) -> None:
    """Refuse examples that are gate-sample claims.

    Args:
        examples: Prompt examples, each with ``qid`` and ``claim``.
        sample_keys: Claim keys of the gate sample.

    Raises:
        ValueError: An example is a sample claim.
    """
    found = [e["claim"] for e in examples if claim_key(e["qid"], e["claim"]) in sample_keys]
    if found:
        raise ValueError(f"prompt examples taken from the sample: {found}")


def classifier_version(
    prompt: str, *, model: str, host: str, reasoning: str, temperature: float, seed: int
) -> str:
    """Return the classifier version: SHA-256 of the prompt and the five call settings."""
    record = {
        "prompt": prompt,
        "model": model,
        "host": host,
        "reasoning": reasoning,
        "temperature": temperature,
        "seed": seed,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def messages(prompt: str, question: str, claim: str) -> list[dict[str, str]]:
    """Return the chat messages for one claim: the question and the claim only."""
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Question: {question}\nSentence: {claim}"},
    ]


def parse_kind(reply: str) -> str:
    """Return the kind in *reply*, or ``unreadable``."""
    word = reply.strip().strip(".").strip().lower()
    return word if word in KINDS else UNREADABLE


async def classify(call: ModelCall, prompt: str, question: str, claim: str) -> str:
    """Classify one claim through *call*."""
    return parse_kind(await call(messages(prompt, question, claim)))


def _todo(run_dir: Path, saved: set[str]) -> list[dict[str, Any]]:
    """Return the claims of a run still to classify, aligned against every judge row."""
    answers = read_rows(run_dir / "answer.jsonl")
    judges = {
        p.name: {r["qid"]: r for r in read_rows(p)} for p in sorted(run_dir.glob("judge-*.jsonl"))
    }
    base = f"{run_dir.parent.parent.name}/{run_dir.parent.name}/{run_dir.name}"
    todo: list[dict[str, Any]] = []
    seen = set(saved)
    for answer in answers:
        qid = answer["qid"]
        for rows in judges.values():
            if qid in rows:
                align(answer, rows[qid], where=f"{base}/{qid}")
        for index, claim in enumerate(answer_claims(answer)):
            key = claim_key(qid, claim)
            if key not in seen:
                seen.add(key)
                todo.append({"claim_key": key, "qid": qid, "index": index, "claim": claim})
    return todo


async def claimkinds_stage(
    run_dir: Path,
    questions: Mapping[str, str],
    call: ModelCall,
    *,
    prompt: str,
    version: str,
    env_check: Callable[[Path], None],
    concurrency: int = 16,
    resume: bool = False,
    stop_errors: tuple[type[BaseException], ...] = (),
) -> int:
    """Classify every claim of one run folder; write ``claim-kinds.jsonl`` there.

    Args:
        run_dir: ``<out>/<dataset>/<setup>/run<n>``.
        questions: Question text by question ID.
        call: The gated model call.
        prompt: The fixed prompt (:func:`build_prompt`).
        version: The classifier version (:func:`classifier_version`).
        env_check: The environment check of task 5.6, run before any call.
        concurrency: Calls in flight (``--classify-concurrency``).
        resume: Skip claims already saved; without it an existing file is refused.
        stop_errors: Exceptions that stop the stage (the gate's rate-limit stop).

    Returns:
        0 when every claim has a kind, or :data:`EXIT_RATE_LIMIT` after a stop.
    """
    out = run_dir / "claim-kinds.jsonl"
    done = run_dir / f".done-{STAGE}.json"
    if out.exists() and not resume:
        raise RuntimeError(f"{out} exists; use --resume")
    env_check(run_dir)
    if done.exists():
        return 0
    saved = {r["claim_key"] for r in read_rows(out)}
    todo = _todo(run_dir, saved)
    gate = asyncio.Semaphore(concurrency)

    async def one(item: dict[str, Any]) -> str:
        async with gate:
            return await classify(call, prompt, questions[item["qid"]], item["claim"])

    results = await asyncio.gather(*(one(i) for i in todo), return_exceptions=True)
    stopped = False
    with out.open("a", encoding="utf-8") as handle:
        for item, kind in zip(todo, results, strict=True):
            if isinstance(kind, stop_errors):
                stopped = True
                continue
            if isinstance(kind, BaseException):
                raise kind
            row = {k: item[k] for k in ("claim_key", "qid", "index")}
            handle.write(json.dumps({**row, "kind": kind, "version": version}) + "\n")
    if stopped:
        return EXIT_RATE_LIMIT
    kinds = Counter(r["kind"] for r in read_rows(out))
    write_json(
        done,
        {"claims": sum(kinds.values()), "kinds": dict(sorted(kinds.items())), "version": version},
    )
    return 0
