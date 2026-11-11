"""Run GLM-5.3 through OMRS's ``chat`` claim judge on the Z.ai Coding Plan (Exp 35, task 6.4).

Two sets, one per call:

- ``aggrefact``: the full LLM-AggreFact TEST split, same fixed order and the
  same row record as ``run_aggrefact.py``. Output
  ``<out>/aggrefact-chat.jsonl``; ``--score`` writes
  ``aggrefact-chat-scores.json`` by the leaderboard rule (balanced accuracy
  per dataset, then the plain mean). GLM-5.3 has no published value, so no
  pass rule applies; the number goes into the 35a plan as the fallback's own.
- ``exp20``: Experiment 20's 120 labelled claim triples. Output
  ``<out>/exp20-chat-<reasoning>.jsonl`` and a summary with unsupported recall
  and false rejection (keep ``low`` when recall >= 0.95 and false rejection
  <= 0.05, else run ``high``).

The judge is OMRS's production ``chat`` strategy built by
``compose_judges.build_judge_target`` from a scratch ``omrs.jsonc``: provider
``openai_compatible`` at the Coding Plan address (judgement log 28), the key
as an ``env://`` reference, filled from the key file and never printed, temperature 0, a
fixed seed and the reasoning level. The model is hosted, so rows run
``--concurrency`` at a time; per-row seconds are not a timing result.
``--resume`` skips rows already written; ``<out>/RUNSTOP`` stops between rows.
No claim, document, key or environment value is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import run_aggrefact as ra

aggrefact_lib = ra.lib
STRATEGY = "chat"
MODEL = "glm-5.3"
BASE_URL = "https://api.z.ai/api/coding/paas/v4"
KEY_ENV = "OMRS_EXP35_ZAI_KEY"  # gitleaks:allow - a variable name, not a key
KEY_REF = f"env://{KEY_ENV}"
KEY_FILE = Path.home() / ".config/omrs/secrets/zai-exp35.key"
JUDGE_SEED = 20261109
EXP20_TRIPLES = (
    ra.PROJECT_ROOT / "experiments/20-citation-faithfulness-2026-09-02/ground-truth.json"
)
DEFAULT_OUT = ra.EXP_DIR / "output" / "prefreeze-glm"


def build_values(reasoning: str) -> dict[str, Any]:
    """Return the scratch ``omrs.jsonc`` values of the GLM-5.3 ``chat`` judge."""
    return {
        "openai_compatible_base_url": BASE_URL,
        "openai_compatible_api_key": KEY_REF,
        "answer": {
            "verify_claims": True,
            "verify_judge": STRATEGY,
            "verify_provider": "openai_compatible",
            "verify_model": MODEL,
            "verify_reasoning": reasoning,
            "verify_temperature": 0,
            "verify_seed": JUDGE_SEED,
        },
    }


def build_judge(out_dir: Path, reasoning: str) -> Any:
    """Write and check the scratch settings, then return OMRS's ``chat`` judge.

    Raises:
        RunError: OMRS builds no ``chat`` judge from the scratch settings.
    """
    from _lib import router_env

    from omrs.compose_judges import build_judge_target, chat_judge
    from omrs.engine_answer import server_seam

    router_env.prepare_environment({}, config_dir=out_dir / "config", state_dir=out_dir / "state")
    if not os.environ.get(KEY_ENV):
        if not KEY_FILE.is_file():
            raise ra.RunError(f"no Z.ai key: set {KEY_ENV} or fill {KEY_FILE.name}")
        os.environ[KEY_ENV] = KEY_FILE.read_text(encoding="utf-8").strip()
    values = build_values(reasoning)
    path = ra.rc.write_settings(values, out_dir / "config")
    ra.rc.check_settings_file(out_dir / "config")
    settings = ra.rc.load_settings()
    ra.rc.check_resolved(settings, values)
    ra.say(f"[config] wrote {path}")
    llm = build_judge_target(settings, settings.answer)
    if llm is None or not hasattr(llm, "acomplete"):
        raise ra.RunError("OMRS built no chat judge LLM from the scratch settings")
    # The production wrap (engine_answer): the chat strategy over the LLM's async seam.
    provider = settings.answer.verify_provider
    judge = chat_judge(llm, settings.answer, provider, lambda inner: server_seam(inner))
    if getattr(judge, "name", None) != STRATEGY:
        raise ra.RunError("OMRS built no chat claim judge from the scratch settings")
    return judge


def make_header(name: str, source_sha256: str, reasoning: str, rows_total: int) -> dict:
    """Return the header line of one run (the keys ``run_aggrefact.prior_state`` compares)."""
    return {
        "kind": "header",
        "format": "omrs-aggrefact-run/1",
        "strategy": STRATEGY,
        "judge_version": ra.judge_version(STRATEGY),
        "model": f"zai-coding/{MODEL}@{reasoning or 'default'}",
        "parquet_sha256": source_sha256,
        "seed": aggrefact_lib.SHUFFLE_SEED,
        "limit": None,
        "rows_total": rows_total,
        "set": name,
    }


def exp20_rows(path: Path | None = None) -> list[dict[str, Any]]:
    """Return Experiment 20's triples as rows (``label`` 1 means supported)."""
    triples = json.loads((path or EXP20_TRIPLES).read_text(encoding="utf-8"))["triples"]
    return [
        {"idx": i, "dataset": t["attack_class"], "claim": t["claim"], "doc": t["evidence"],
         "label": int(t["label"] == aggrefact_lib.SUPPORTED)}
        for i, t in enumerate(triples)
    ]  # fmt: skip


async def run_concurrent(
    judge: Any, rows: Sequence[Mapping[str, Any]], todo: Sequence[int], writer: Any,
    *, concurrency: int, have_facts: bool, stop_file: Path,
) -> int:  # fmt: skip
    """Judge *todo* with at most *concurrency* calls in flight; return the exit code.

    Rows are written as they finish, so the file order is not the queue order.
    """
    from omrs.core.answer.judges.base import JudgeUnavailable

    queue = list(todo)
    state = {"facts": have_facts, "failures": 0, "done": 0, "code": 0}

    async def worker() -> None:
        while queue and state["code"] == 0 and not stop_file.exists():
            idx = queue.pop(0)
            try:
                record, call = await ra.judge_one(judge, rows[idx])
            except JudgeUnavailable as unavailable:
                ra.say(f"[error] {unavailable.reason}")
                state["code"] = ra.EXIT_UNAVAILABLE
                return
            writer.write(record)
            if call is not None and record["error"] is None and not state["facts"]:
                writer.write(ra.facts_record(STRATEGY, call))
                state["facts"] = True
            state["failures"] = state["failures"] + 1 if record["error"] else 0
            if state["failures"] > ra.MAX_CONSECUTIVE_FAILURES:
                failed, last = state["failures"], record["error"]
                ra.say(f"[error] {failed} rows in a row failed (last: {last})")
                state["code"] = ra.EXIT_FAILURES
                return
            state["done"] += 1
            if state["done"] % 500 == 0:
                ra.say(f"[progress] {state['done']} of {len(todo)} rows")

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    if stop_file.exists():
        ra.say(f"[stop] {stop_file.name} found; {state['done']} rows judged")
    elif state["code"] == 0:
        ra.say(f"[done] {state['done']} rows judged")
    return state["code"]


def exp20_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return unsupported recall and false rejection of an Experiment 20 run.

    A failed row has no verdict: it counts in ``errors`` only, never as caught or
    rejected, and any failed row blocks ``keep_low``.
    """
    judged = [r for r in rows if not r["error"]]
    unsupported = [r for r in judged if r["label"] == 0]
    supported = [r for r in judged if r["label"] == 1]
    caught = sum(not aggrefact_lib.predicted_supported(r["verdict"]) for r in unsupported)
    rejected = sum(not aggrefact_lib.predicted_supported(r["verdict"]) for r in supported)
    recall = caught / len(unsupported) if unsupported else None
    false_rejection = rejected / len(supported) if supported else None
    errors = len(rows) - len(judged)
    keep_low = (
        errors == 0 and recall is not None and recall >= 0.95 and (false_rejection or 0) <= 0.05
    )
    return {"n": len(rows), "unsupported_recall": recall, "false_rejection": false_rejection,
            "errors": errors, "keep_low": keep_low}  # fmt: skip


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", required=True, choices=["aggrefact", "exp20"])
    parser.add_argument("--reasoning", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--score", action="store_true", help="score the finished file only")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--parquet", type=Path, default=ra.DEFAULT_PARQUET)
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        parser.error("--concurrency must be 1 or more")
    return args


def result_path(args: argparse.Namespace) -> Path:
    """Return the result file of *args*."""
    if args.set == "aggrefact":
        return args.out_dir / f"aggrefact-{STRATEGY}.jsonl"
    return args.out_dir / f"exp20-{STRATEGY}-{args.reasoning}.jsonl"


def score(args: argparse.Namespace) -> dict[str, Any]:
    """Score the finished result file; write ``<file>-scores.json`` atomically."""
    path = result_path(args)
    _header, _facts, rows = aggrefact_lib.read_results(path)
    summary = (aggrefact_lib.leaderboard(rows) if args.set == "aggrefact"
               else exp20_summary(rows))  # fmt: skip
    target = path.with_name(path.stem + "-scores.json")
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    ra.say(f"[score] wrote {target.name}")
    return summary


def main(argv: Sequence[str] | None = None, *, make_judge: Any = None) -> int:
    """Run or score one set; return the exit code. *make_judge* replaces the real judge (tests)."""
    args = parse_args(argv)
    try:
        if args.score:
            ra.say(json.dumps(score(args), sort_keys=True))
            return 0
        return asyncio.run(_run(args, make_judge or build_judge))
    except (ra.RunError, ra.rc.RouterConfigError, aggrefact_lib.ScoreError) as error:
        ra.say(f"[error] {error}")
        return 2


async def _run(args: argparse.Namespace, make_judge: Any) -> int:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.set == "aggrefact":
        source_sha = aggrefact_lib.file_sha256(args.parquet)
        if source_sha != aggrefact_lib.PARQUET_SHA256:
            raise ra.RunError(f"{args.parquet.name} is not the pinned TEST split")
        rows = aggrefact_lib.load_rows(args.parquet)
        order = aggrefact_lib.row_order(len(rows), aggrefact_lib.SHUFFLE_SEED)
    else:
        source_sha = aggrefact_lib.file_sha256(EXP20_TRIPLES)
        rows = exp20_rows()
        order = list(range(len(rows)))
    results = result_path(args)
    header = make_header(args.set, source_sha, args.reasoning, len(rows))
    done, have_facts = ra.prior_state(results, header, resume=args.resume)
    todo = [idx for idx in order if idx not in done]
    ra.say(f"[run] {args.set}: {len(order)} rows, {len(done)} done, {len(todo)} to do")
    judge = make_judge(args.out_dir, args.reasoning)
    writer = ra.Writer(results)
    try:
        if not done and results.stat().st_size == 0:
            writer.write(header)
        return await run_concurrent(
            judge,
            rows,
            todo,
            writer,
            concurrency=args.concurrency,
            have_facts=have_facts,
            stop_file=args.out_dir / "RUNSTOP",
        )
    finally:
        writer.close()


if __name__ == "__main__":
    sys.exit(main())
