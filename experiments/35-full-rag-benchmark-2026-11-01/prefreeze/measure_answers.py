"""Price the main run: 20 real answers and their Ragas judging (Exp 35 pre-freeze, task 6.3).

Stages, each resuming from its own file in ``--out-dir``:

1. ``ingest``: Experiment 48 Part A's fixed set (6 Experiment 3 documents and
   5 FinanceBench PDFs) into a scratch LanceDB, with Experiment 48's own code
   and the local Qwen3-Embedding-4B through OMRS's managed router.
2. ``answers``: a seeded sample of Part A's 42 questions through
   ``Engine.answer`` on OpenRouter (``answer.*`` settings), to ``answers20.jsonl``.
3. ``ragas``: Ragas 0.4.3, four metrics, judge ``openai/gpt-oss-120b`` built by
   OMRS's judge builder (``answer.verify_*`` settings), to ``ragas20.jsonl``.
4. ``summary``: tokens, seconds, calls and dollars, to ``measure-summary.json``.

Output files hold ids and numbers only. Question, answer, context and
reference text stay in memory, so a Ragas row whose answer ran in an earlier
process asks the question again (``reanswered: true``; not priced twice).

Run on the pod (heavy-run rule: the operator runs it):
    SWEEP_GGUF_DIR=... OPENROUTER_API_KEY=... uv run --no-sync python \
        experiments/35-full-rag-benchmark-2026-11-01/prefreeze/measure_answers.py \
        --answer-host <slug> --judge-host <slug> --prices prices.json \
        --ragas-venv /workspace/ragas-venv
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXP_DIR = HERE.parent
PROJECT_ROOT = EXP_DIR.parent.parent
EXP48_DIR = PROJECT_ROOT / "experiments" / "48-pipeline-sweep-llamacpp-2026-11-01"
DEFAULT_OUT = EXP_DIR / "output" / "prefreeze"
COLLECTION = "prefreeze20"
STAGES = ("ingest", "answers", "ragas", "summary")

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import measure_lib as lib  # noqa: E402
from ragas_stage import MetricFn, RagasMissingError, RecordingSeam, judge_answer  # noqa: E402

CONFIGURED = {"model": lib.ANSWER_MODEL, "temperature": lib.TEMPERATURE, "seed": lib.SEED}


@dataclass(frozen=True)
class Options:
    """What one run does and where it writes."""

    out_dir: Path
    stages: tuple[str, ...] = STAGES
    resume: bool = False
    prices: Path | None = None


@dataclass
class Deps:
    """The outside world one run needs; tests pass stubs.

    Attributes:
        answer: Answers one question text; returns the ``Engine.answer`` result.
        ingest: Ingests the fixed set; returns one row per file.
        judge: Builds ``(seam, metrics, header)`` for the Ragas stage.
        require_ragas: Returns the Ragas version or raises :class:`RagasMissingError`.
    """

    answer: Callable[[str], Awaitable[dict]]
    ingest: Callable[[], list[dict]] | None = None
    judge: Callable[[], tuple[RecordingSeam, Mapping[str, MetricFn], dict]] | None = None
    require_ragas: Callable[[], str] | None = None


async def run_stages(opts: Options, deps: Deps, questions: Sequence[Mapping[str, Any]]) -> int:
    """Run the chosen stages in order; return the exit code (2: Ragas missing)."""
    out = opts.out_dir
    if "ragas" in opts.stages:
        try:
            (deps.require_ragas or _no_ragas_check)()
        except RagasMissingError as exc:  # before any stage, so nothing is spent
            print(f"[ragas] {exc}", file=sys.stderr, flush=True)
            return 2
    if "ingest" in opts.stages:
        _stage_ingest(out / "ingest.jsonl", deps, opts.resume)
    texts: dict[str, dict[str, Any]] = {}
    if "answers" in opts.stages:
        await _stage_answers(out / "answers20.jsonl", deps, questions, opts.resume, texts)
    if "ragas" in opts.stages:
        await _stage_ragas(out, deps, questions, opts.resume, texts)
    if "summary" in opts.stages:
        _stage_summary(out, opts.prices)
    return 0


def _no_ragas_check() -> str:
    raise RagasMissingError("no Ragas check was given")


def _stage_ingest(path: Path, deps: Deps, resume: bool) -> None:
    if resume and path.exists():
        print(f"[ingest] done earlier: {path.name}", flush=True)
        return
    if deps.ingest is None:
        raise RuntimeError("the ingest stage has no ingest function")
    rows = [{k: r.get(k) for k in ("file", "seconds", "error")} for r in deps.ingest()]
    lib.write_jsonl_atomic(path, rows)


def _texts_of(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "answer": str(result.get("answer") or ""),
        "contexts": [str(e.get("text") or "") for e in result.get("evidence") or []],
    }


async def _answer_one(deps: Deps, question: Mapping[str, Any]) -> tuple[dict, float, str]:
    started, error, result = time.perf_counter(), "", {}
    try:
        result = await deps.answer(question["question"])
    except Exception as exc:  # noqa: BLE001 - record and continue (Exp 48 D4)
        error = f"{type(exc).__name__}: {exc}"
    return result or {}, time.perf_counter() - started, error


async def _stage_answers(
    path: Path,
    deps: Deps,
    questions: Sequence[Mapping[str, Any]],
    resume: bool,
    texts: dict[str, dict[str, Any]],
) -> None:
    lib.check_fresh(path, resume)
    done = {row["qid"] for row in lib.read_rows(path)}
    for question in questions:
        if question["qid"] in done:
            continue
        result, seconds, error = await _answer_one(deps, question)
        row = lib.answer_row(question, result, seconds, error, CONFIGURED)
        lib.append_row(path, row)
        if not row["error"]:
            texts[question["qid"]] = _texts_of(result)
        print(
            f"[answer] {question['qid']}: {row['seconds']}s host={row['host']}"
            + (" ERROR" if row["error"] else ""),
            flush=True,
        )


async def _stage_ragas(
    out: Path,
    deps: Deps,
    questions: Sequence[Mapping[str, Any]],
    resume: bool,
    texts: dict[str, dict[str, Any]],
) -> None:
    path = out / "ragas20.jsonl"
    lib.check_fresh(path, resume)
    done = {row["qid"] for row in lib.read_rows(path)}
    answered = {row["qid"]: row for row in lib.read_rows(out / "answers20.jsonl")}
    if deps.judge is None:
        raise RuntimeError("the ragas stage has no judge")
    seam, metrics, header = deps.judge()
    for question in questions:
        qid = question["qid"]
        if qid in done:
            continue
        row = await _judge_one(
            deps, question, answered.get(qid), texts.get(qid), seam, metrics, header
        )
        lib.append_row(path, row)
        print(
            f"[ragas] {qid}: {len(row.get('calls', []))} calls"
            + (f" ERROR {row['error']}" if row["error"] else ""),
            flush=True,
        )


async def _judge_one(
    deps: Deps,
    question: Mapping[str, Any],
    answer: Mapping | None,
    text: dict[str, Any] | None,
    seam: RecordingSeam,
    metrics: Mapping[str, MetricFn],
    header: Mapping[str, Any],
) -> dict:
    base = {**header, "qid": question["qid"], "metrics": {}, "calls": [], "reanswered": False}
    if answer is None:
        return {**base, "error": "no answers20 row: run the answers stage first"}
    if answer.get("error"):
        return {**base, "error": "answer failed; not judged"}
    reanswered = text is None
    if text is None:  # the answer ran in an earlier process; its text was never saved
        result, _, error = await _answer_one(deps, question)
        if error or not result or result.get("status") == "error":
            return {**base, "reanswered": True, "error": "re-answer failed; not judged"}
        text = _texts_of(result)
    sample = {
        "qid": question["qid"],
        "question": question["question"],
        "reference": question.get("reference", ""),
        **text,
    }
    return await judge_answer(sample, seam, metrics, header={**header, "reanswered": reanswered})


def _stage_summary(out: Path, prices_path: Path | None) -> None:
    answers = lib.read_rows(out / "answers20.jsonl")
    ragas = lib.read_rows(out / "ragas20.jsonl")
    cost = None
    if prices_path is not None:
        cost = lib.cost_block(answers, ragas, lib.load_prices(prices_path))
    runtime = out / "runtime.json"
    lib.write_json_atomic(
        out / "measure-summary.json",
        {
            "answer": {**CONFIGURED},
            "judge": {
                "model": lib.JUDGE_MODEL,
                "reasoning": lib.JUDGE_REASONING,
                "temperature": lib.TEMPERATURE,
                "seed": lib.SEED,
            },
            "answers": lib.answer_summary(answers),
            "ragas": lib.ragas_summary(ragas),
            "cost": cost,
            "cost_note": None if cost is not None else "no --prices given",
            "runtime_record": runtime.name if runtime.exists() else None,
        },
    )
    print(f"[summary] {out / 'measure-summary.json'}", flush=True)


def parse_stages(text: str) -> tuple[str, ...]:
    """Return the stage names of a comma list, in run order."""
    names = {part.strip() for part in text.split(",") if part.strip()}
    unknown = names - set(STAGES)
    if unknown:
        raise SystemExit(f"unknown stage(s): {', '.join(sorted(unknown))}; use {','.join(STAGES)}")
    return tuple(s for s in STAGES if s in names)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, default=lib.DEFAULT_LIMIT)
    parser.add_argument("--resume", action="store_true", help="continue each stage file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="load inputs, write scratch settings, print the plan; start nothing",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stages", type=parse_stages, default=STAGES)
    parser.add_argument("--prices", type=Path, help="prices.json written by the pod script")
    parser.add_argument("--answer-host", default="", help="OpenRouter host slug for answers")
    parser.add_argument("--judge-host", default="", help="OpenRouter host slug for the judge")
    parser.add_argument("--ragas-venv", type=Path, help="venv holding ragas==0.4.3")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the measurement; return the exit code."""
    import measure_live  # imports Experiment 48 and OMRS; tests never reach this line

    args = parse_args(argv)
    hosts = {"answer": args.answer_host.strip(), "judge": args.judge_host.strip()}
    out = args.out_dir.resolve()
    wiring = measure_live.Wiring(
        out_dir=out, answer_host=hosts["answer"], judge_host=hosts["judge"], collection=COLLECTION
    )
    questions = lib.sample_questions(wiring.question_pool(), args.limit)
    settings_path = wiring.configure()
    if args.dry_run:
        return wiring.print_plan(settings_path, args.stages, [q["qid"] for q in questions])
    if not (hosts["answer"] and ("ragas" not in args.stages or hosts["judge"])):
        raise SystemExit("a live run needs --answer-host (and --judge-host for the ragas stage)")
    if "OPENROUTER_API_KEY" not in os.environ:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    opts = Options(out_dir=out, stages=args.stages, resume=args.resume, prices=args.prices)
    return wiring.run(opts, questions, args.ragas_venv, run_stages, Deps)


if __name__ == "__main__":
    raise SystemExit(main())
