"""Length-controlled check of Experiment 35 (task 16.19; pre-registration section 11.2).

A registered sensitivity analysis with no gate. ``--stage lengthcheck`` draws
300 cited claims from the ``c2048`` crossed answers of the core datasets
(seed 20261119; refusal claims left out, as in the faithfulness pool). Each
cited evidence text is split into consecutive 512-token windows (pinned Qwen3
tokenizer); the window that shares the most distinct lower-case claim words
is kept, ties to the earlier window. GLM-5.3 (``chat``) and Clef-Flash judge
the claim again on those windows. The report gives, per checker, the share of
claims whose verdict changed against the saved verdict, with a Wilson interval.

Resend rule (section 12): a failed judge call saves no row and is sent again
on ``--resume``; its third error closes it as missing. A rate limit past the
attempts stops the stage with exit code 5. Drop step 2 (``drops.json``)
removes the check: the stage then writes nothing.

Files in ``<out>/lengthcheck/``: ``sample.json``, ``lengthcheck.jsonl`` (one row
per claim and checker: ``id``, ``item_id``, ``checker``, ``original``,
``windowed``) and ``lengthcheck.json`` (the report).

The runner runs it with ``--judges chat,clef_flash`` and builds each checker
through ``ctx.judge(name)`` (an OMRS claim judge with ``async judge(claim,
texts)``); tests put the judges on ``ctx.judges`` instead. ``ctx.offsets``
maps text to token character spans; the pinned Qwen3 tokenizer when absent.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import arms
import budget35
import claimkinds35
import correct35
import outputs35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import OrderedRows
from experiments._lib.stats_d6 import wilson
from faithpool35 import chunk_size
from outputs35 import read_rows, say, write_json
from stages35 import StageIncomplete, StageOrderError

from omrs.core.answer.verify import split_claims

__all__ = ["EXIT_RATE_LIMIT", "StageIncomplete", "lengthcheck_stage"]

SEED = 20261119
CLAIMS = 300
WINDOW = 512
CHUNK = 2048
CHECKERS = ("chat", "clef_flash")
DROP_STEP = 2
EXIT_RATE_LIMIT = 5
VERDICTS = ("supported", "unsupported")
_WORD = re.compile(r"\w+")


def _verdicts(folder: Path, checker: str, answer: Mapping[str, Any]) -> dict[int, Any]:
    rows = {str(r["qid"]): r for r in read_rows(folder / f"judge-{checker}.jsonl")}
    judge = rows.get(str(answer["qid"]))
    if judge is None or judge.get("missing"):
        return {}
    where = f"{folder}/{answer['qid']}"
    return {
        i: v.get("verdict")
        for i, (_, v) in enumerate(claimkinds35.align(answer, judge, where=where))
    }


def pool(out: Path) -> list[dict[str, Any]]:
    """Return the cited non-refusal claims of the ``c2048`` crossed answers, core datasets."""
    claims: list[dict[str, Any]] = []
    for dataset, setup, run, folder in outputs35.Layout(out).need_runs("answer", "answer.jsonl"):
        if dataset not in correct35.CORE or arms.parse_setup(setup).t20k:
            continue
        if chunk_size(setup) != CHUNK:
            continue
        refusals = {
            r["claim_key"]
            for r in read_rows(folder / "claim-kinds.jsonl")
            if r.get("kind") == "refusal" and not r.get("uncited")
        }
        for answer in read_rows(folder / "answer.jsonl"):
            if answer.get("missing"):
                continue
            evidence = answer.get("evidence") or []
            texts = {e["ordinal"]: e["text"] for e in evidence}
            saved = {c: _verdicts(folder, c, answer) for c in CHECKERS}
            qid = str(answer["qid"])
            for index, (claim, ordinals) in enumerate(
                split_claims(answer.get("answer") or "", len(evidence))
            ):
                if claimkinds35.claim_key(qid, claim) in refusals:
                    continue
                claims.append(
                    {
                        "item_id": correct35.item_id(
                            "lengthcheck", dataset, setup, run, qid, index
                        ),
                        "dataset": dataset,
                        "setup": setup,
                        "run": run,
                        "qid": qid,
                        "index": index,
                        "claim": claim,
                        "passages": [texts[o] for o in ordinals if o in texts],
                        "original": {c: saved[c].get(index) for c in CHECKERS},
                    }
                )
    return claims


def draw(claims: Sequence[Mapping[str, Any]], *, seed: int = SEED, n: int = CLAIMS) -> list[dict]:
    """Draw *n* claims (all when fewer) with ``random.Random(seed)`` from the sorted pool."""
    ordered = sorted((dict(c) for c in claims), key=lambda c: c["item_id"])
    return random.Random(seed).sample(ordered, min(n, len(ordered)))  # noqa: S311 - seeded draw


def windows(text: str, offsets: Sequence[tuple[int, int]], size: int = WINDOW) -> list[str]:
    """Split *text* into consecutive windows of *size* tokens, given each token's character span."""
    if not offsets:
        return [text]
    return [
        text[offsets[i][0] : offsets[min(i + size, len(offsets)) - 1][1]]
        for i in range(0, len(offsets), size)
    ]


def best_window(claim: str, found: Sequence[str]) -> str:
    """Return the window sharing most distinct lower-case claim words; ties go to the earlier."""
    words = set(_WORD.findall(claim.lower()))
    shared = [len(words & set(_WORD.findall(w.lower()))) for w in found]
    return found[shared.index(max(shared))]


def _qwen3_offsets() -> Callable[[str], list[tuple[int, int]]]:
    from omrs.integrations.tokenizer import load_tokenizer

    tokenizer = load_tokenizer(arms.TOKENIZER_MODEL, arms.TOKENIZER_REVISION)
    return lambda text: list(tokenizer.encode(text, add_special_tokens=False).offsets)


def report(rows: Sequence[Mapping[str, Any]], claims: int) -> dict[str, Any]:
    """Return the verdict change rate per checker with its Wilson interval (no gate)."""
    out: dict[str, Any] = {"seed": SEED, "claims": claims, "window_tokens": WINDOW}
    for checker in CHECKERS:
        mine = [r for r in rows if str(r["id"]).endswith(f"|{checker}")]
        paired = [
            r for r in mine if r.get("original") in VERDICTS and r.get("windowed") in VERDICTS
        ]
        changed = sum(r["original"] != r["windowed"] for r in paired)
        low, high = wilson(changed, len(paired))
        out[checker] = {
            "n": len(paired),
            "changed": changed,
            "rate": changed / len(paired) if paired else None,
            "low": low,
            "high": high,
            "missing": sum(1 for r in mine if r.get("missing")),
        }
    return out


async def lengthcheck_stage(ctx: Any) -> int:
    """Run the length-controlled check over the output folder; return 0 or 5.

    Raises:
        StageIncomplete: A judge call stays open after its errors; ``--resume`` sends it again.
        StageOrderError: ``--judges`` does not name both checkers.
    """
    missing = [c for c in CHECKERS if c not in arms.parse_judges(ctx.args.judges)]
    if missing:
        raise StageOrderError(f"the lengthcheck stage needs --judges {','.join(CHECKERS)}")
    judges = getattr(ctx, "judges", None) or {c: ctx.judge(c) for c in CHECKERS}
    out = ctx.layout.root
    if DROP_STEP in budget35.read_drops(out):
        say("[lengthcheck] drop step 2 removed the length-controlled check; nothing to do")
        return 0
    folder = out / "lengthcheck"
    folder.mkdir(parents=True, exist_ok=True)
    sample = draw(pool(out))
    write_json(folder / "sample.json", {"seed": SEED, "items": sample})
    offsets = getattr(ctx, "offsets", None) or _qwen3_offsets()
    gate = HostedGate("lengthcheck", 1, attempts=int(ctx.args.rate_limit_attempts))
    by_id = {f"{c['item_id']}|{k}": (c, k) for c in sample for k in CHECKERS}
    with outputs35.RowFile(folder, "lengthcheck", ctx.key, resume=ctx.resume) as log:
        rows = OrderedRows(log, list(by_id), id_field="id")
        for item_id in rows.todo():
            claim, checker = by_id[item_id]
            texts = [best_window(claim["claim"], windows(p, offsets(p))) for p in claim["passages"]]
            rows.dispatch(item_id)
            try:
                judge = judges[checker].judge
                result = await gate.call(lambda j=judge, c=claim["claim"], t=texts: j(c, t))
                error = getattr(getattr(result, "call", None), "error", None)
                if error:
                    raise RuntimeError(f"judge call failed: {error}")
            except RateLimitStop as exc:
                say(f"[lengthcheck] stopped: {exc}")
                return EXIT_RATE_LIMIT
            except Exception as exc:  # noqa: BLE001 - an error is not a result (section 12)
                rows.fail(item_id, f"{type(exc).__name__}: {exc}"[:500])
                continue
            rows.submit(
                item_id,
                {
                    "id": item_id,
                    "item_id": claim["item_id"],
                    "checker": checker,
                    "original": claim["original"][checker],
                    "windowed": result.verdict,
                },
            )
        if not rows.finish({"claims": len(sample)}):
            raise StageIncomplete("lengthcheck: judge calls still open")
        result_report = report(log.rows(), len(sample))
    write_json(folder / "lengthcheck.json", result_report)
    say(f"[lengthcheck] {len(sample)} claims judged again on 512-token windows")
    return 0
