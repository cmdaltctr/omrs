"""Run the LLM-AggreFact TEST split through one OMRS claim judge (Exp 35 pre-freeze, task 6.3).

One strategy per process: ``clef_flash`` or ``granite_guardian``. Each row is
one ``judge.judge(claim, [doc])`` call, sent one at a time (root gotcha 16:
a queued request's time includes waiting).

Settings and router (the Experiment 48 mechanism): the run writes
``<out>/config/omrs.jsonc`` with one ``llamacpp_models`` entry for the judge
model, a ``managed`` router on ``127.0.0.1:18080`` and
``answer.verify_claims=true``, ``answer.verify_judge=<strategy>`` and
``answer.verify_model=<model>``. ``OMRS_CONFIG_DIR`` and ``OMRS_STATE_DIR``
point inside ``<out>``. Experiment 48's ``router_config.start_router`` starts
OMRS's own managed router; ``compose_judges.build_judge_target`` builds the
production judge. ``SWEEP_GGUF_DIR`` names the folder of the GGUF file.

Output: ``<out>/aggrefact-<strategy>.jsonl``. Line 1 is the header; one
``facts`` line follows the first successful call; then one ``row`` line per
row. Each line is flushed. ``--resume`` skips the rows already written and
refuses a header that differs. ``<out>/RUNSTOP`` stops the run between rows,
and SIGTERM or Ctrl-C stops it after the current row. No claim text, document
text, key or environment value is printed. Heavy-run rule: tell the operator
before a run without ``--dry-run``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

PREFREEZE = Path(__file__).resolve().parent
EXP_DIR = PREFREEZE.parent
PROJECT_ROOT = EXP_DIR.parent.parent
EXP48 = PROJECT_ROOT / "experiments" / "48-pipeline-sweep-llamacpp-2026-11-01"
DEFAULT_OUT = EXP_DIR / "output" / "prefreeze"
DEFAULT_PARQUET = (
    Path.home() / "Development/DATA/omrs/benchmarks/llm-aggrefact/data/test-00000-of-00001.parquet"
)

for _folder in (PREFREEZE, EXP48, PROJECT_ROOT / "experiments"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import aggrefact_lib as lib  # noqa: E402
import router_config as rc  # noqa: E402

#: The judge models (design D10, D13). ``sha256`` ``None``: hashed before the router starts.
JUDGES: Mapping[str, Mapping[str, Any]] = {
    "clef_flash": {
        "role": "judge-clef-flash",
        "repository": "ggml-org/Clef-Flash-GGUF",
        "file": "Clef-Flash-Q8_0.gguf",
        # Recorded in experiments/47-router-confirmation-2026-11-05/plan.json.
        "sha256": "25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e",
    },
    "granite_guardian": {
        "role": "judge-granite-guardian",
        "repository": "ibm-granite/granite-guardian-3.3-8b-GGUF",
        # Not yet checked against the downloaded file: pass --gguf-file when it differs.
        "file": "granite-guardian-3.3-8b-Q8_0.gguf",
        "sha256": None,
    },
}
#: The router preset of the judge entry: Experiment 48's chat preset, one slot.
SERVER_ARGS: Mapping[str, Any] = {
    "ctx-size": 32768,
    "parallel": 1,
    "flash-attn": True,
    "n-gpu-layers": "all",
    "fit": False,
    "cache-type-k": "f16",
    "cache-type-v": "f16",
    "spec-type": "none",
    "cache-prompt": False,
    "cache-reuse": 0,
}
HEADER_KEYS = (
    "strategy", "judge_version", "model", "parquet_sha256", "seed", "limit", "rows_total",
)  # fmt: skip
TIMING_ROWS = 200
MAX_CONSECUTIVE_FAILURES = 20
EXIT_FAILURES = 3
EXIT_UNAVAILABLE = 4

MakeJudge = Callable[[str, Path, str | None], Any]


class RunError(RuntimeError):
    """The run cannot start or continue. The message is plain and holds no row text."""


def say(text: str) -> None:
    """Print one progress line and flush it."""
    print(text, flush=True)


# --- the judge model, the scratch settings and the router -----------------------


def judge_model(strategy: str, gguf_file: str | None = None, sha256: str | None = None) -> dict:
    """Return the plan-style model record of *strategy* (the shape Exp 48 reads)."""
    spec = JUDGES[strategy]
    return {
        "role": spec["role"],
        "repository": spec["repository"],
        "file": gguf_file or spec["file"],
        "sha256": sha256 or spec["sha256"],
        "server_args": dict(SERVER_ARGS),
    }


def model_id(strategy: str) -> str:
    """Return the router request name of *strategy*'s model (``<repository>:<quant>``)."""
    return rc.model_name(judge_model(strategy))


def judge_version(strategy: str) -> str:
    """Return the prompt-format version of *strategy* from OMRS's registry."""
    from omrs.core.answer.judges import registry

    return str(registry.get(strategy).VERSION)


def build_values(strategy: str, folder: Path, model: Mapping[str, Any]) -> dict[str, Any]:
    """Return the ``omrs.jsonc`` values of one judge run.

    Raises:
        RouterConfigError: The model file is missing, or OMRS refuses the preset.
    """
    plan = {"runtime": {"models": [model]}}
    return {
        "local_backend": "llamacpp",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": rc.ROUTER_URL,
        "llamacpp_router_models_max": 1,
        "answer": {
            "verify_claims": True,
            "verify_judge": strategy,
            "verify_model": rc.model_name(model),
            "verify_provider": "local",
        },
        "llamacpp_models": rc.model_entries(plan, folder),
    }


def configure(
    strategy: str, out_dir: Path, gguf_file: str | None, *, hash_missing: bool
) -> tuple[dict, Any, Path]:
    """Point OMRS at ``<out>``, write and check the scratch file; return (model, settings, path).

    With *hash_missing*, a model without a recorded SHA-256 is hashed now, so
    the router checks it and each call record names it.
    """
    from _lib import router_env

    router_env.prepare_environment({}, config_dir=out_dir / "config", state_dir=out_dir / "state")
    folder = router_env.gguf_dir()
    model = judge_model(strategy, gguf_file)
    if hash_missing and not model["sha256"] and (folder / model["file"]).is_file():
        say(f"[gguf] hashing {model['file']} (no recorded SHA-256)")
        model["sha256"] = lib.file_sha256(folder / model["file"])
        say(f"[gguf] sha256 {model['sha256']}")
    values = build_values(strategy, folder, model)
    path = rc.write_settings(values, out_dir / "config")
    rc.check_settings_file(out_dir / "config")
    settings = rc.load_settings()
    rc.check_resolved(settings, values)
    return model, settings, path


def settings_summary(strategy: str, settings: Any, path: Path) -> dict[str, Any]:
    """Return what OMRS resolved for the judge run; sends nothing and starts nothing."""
    from omrs.compose_answer import llamacpp_roles
    from omrs.compose_judges import strategy_ready

    answer = settings.answer
    return {
        "config_file": str(path),
        "llamacpp_router_server": settings.llamacpp_router_server,
        "llamacpp_router_url": settings.llamacpp_router_url,
        "llamacpp_router_models_max": settings.llamacpp_router_models_max,
        "verify_claims": answer.verify_claims,
        "verify_judge": answer.verify_judge,
        "verify_model": answer.verify_model,
        "entries": {
            e.model: {"file": Path(e.file or "").name, "sha256": e.sha256, "preset": dict(e.preset)}
            for e in settings.llamacpp_models.values()
        },
        "judge_role_problems": [
            list(p) for p in llamacpp_roles(settings).problems if p[0] == "judge"
        ],
        "strategy_ready": strategy_ready(settings, strategy, answer) or "ready",
    }


def production_judge(strategy: str, out_dir: Path, gguf_file: str | None) -> Any:
    """Start OMRS's managed router with the judge model and return the production judge.

    Raises:
        RunError: OMRS reports the strategy cannot run, or builds no judge.
    """
    from omrs.compose_judges import build_judge_target, strategy_ready

    model, settings, path = configure(strategy, out_dir, gguf_file, hash_missing=True)
    say(f"[config] wrote {path}")
    reason = strategy_ready(settings, strategy, settings.answer)
    if reason:
        raise RunError(f"OMRS says {strategy} cannot run: {reason}")
    rc.start_router([model["file"]], {"runtime": {"models": [model]}})
    judge = build_judge_target(settings, settings.answer)
    if judge is None or getattr(judge, "name", None) != strategy:
        raise RunError(f"OMRS built no {strategy} claim judge from the scratch settings")
    return judge


# --- the result file ---------------------------------------------------------------


def make_header(strategy: str, parquet_sha256: str, limit: int | None, rows_total: int) -> dict:
    """Return the header line of one run."""
    return {
        "kind": "header",
        "format": "omrs-aggrefact-run/1",
        "strategy": strategy,
        "judge_version": judge_version(strategy),
        "model": model_id(strategy),
        "parquet_sha256": parquet_sha256,
        "seed": lib.SHUFFLE_SEED,
        "limit": limit,
        "rows_total": rows_total,
    }


def _drop_partial_last_line(path: Path) -> None:
    """Remove a last line a killed run left half-written (atomic rewrite)."""
    text = path.read_text(encoding="utf-8")
    if not text or text.endswith("\n"):
        return
    kept = text[: text.rfind("\n") + 1]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(kept, encoding="utf-8")
    tmp.replace(path)
    say("[resume] dropped a half-written last line")


def prior_state(path: Path, header: Mapping[str, Any], *, resume: bool) -> tuple[set[int], bool]:
    """Return the row indexes already written and whether a ``facts`` line exists.

    Raises:
        RunError: The file exists without ``--resume``, or its header differs.
    """
    if not path.exists():
        return set(), False
    if not resume:
        raise RunError(
            f"{path.name} exists; pass --resume to continue it, or use another --out-dir"
        )
    _drop_partial_last_line(path)
    try:
        found, facts, rows = lib.read_results(path)
    except lib.ScoreError as error:
        raise RunError(str(error)) from None
    differ = [key for key in HEADER_KEYS if found.get(key) != header.get(key)]
    if differ:
        text = "; ".join(f"{k}: file {found.get(k)!r}, run {header.get(k)!r}" for k in differ)
        raise RunError(f"--resume refused: the header of {path.name} differs ({text})")
    return {int(row["idx"]) for row in rows}, facts is not None


class Writer:
    """Append JSON lines to the result file; flush and sync each line."""

    def __init__(self, path: Path) -> None:
        """Open *path* for appending."""
        self._handle = path.open("a", encoding="utf-8")

    def write(self, record: Mapping[str, Any]) -> None:
        """Write one record as one line."""
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def close(self) -> None:
        """Close the file."""
        self._handle.close()


# --- the row loop ------------------------------------------------------------------


def facts_record(strategy: str, call: Any) -> dict[str, Any]:
    """Return the ``facts`` line of the first successful call (names the exact GGUF)."""
    return {
        "kind": "facts",
        "strategy": strategy,
        "model": call.model,
        "sha256": call.sha256,
        "version": call.version,
        "host": call.host,
        "settings": dict(call.settings),
    }


async def judge_one(judge: Any, row: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    """Judge one row; return its ``row`` record and the call record (or ``None``).

    Raises:
        JudgeUnavailable: The judge cannot start; nothing was sent.
    """
    from omrs.core.answer.judges.base import JudgeUnavailable

    started = time.perf_counter()
    call, verdict, error = None, None, None
    try:
        judgement = await judge.judge(row["claim"], [row["doc"]])
        call, verdict = judgement.call, judgement.verdict
        error = getattr(call, "error", None)
    except JudgeUnavailable:
        raise
    except Exception as failure:  # noqa: BLE001 - one fixed reason per row, never the text
        error = f"exception-{type(failure).__name__}"
    record = {
        "kind": "row",
        "idx": row["idx"],
        "dataset": row["dataset"],
        "label": int(row["label"]),
        "verdict": verdict,
        "p_yes": getattr(call, "p_yes", None),
        "seconds": round(time.perf_counter() - started, 4),
        "error": error,
    }
    return record, call


def timing_line(done: int, elapsed: float, remaining: int, total: int) -> str:
    """Return the one timing line: items per second and the ETAs."""
    rate = done / elapsed if elapsed > 0 else float("inf")
    hours = (lambda n: n / rate / 3600) if rate > 0 else (lambda n: float("inf"))
    return (
        f"[timing] first {done} rows: {rate:.3f} items/s; full set of {total} rows "
        f"about {hours(total):.2f} h; remaining {remaining} rows of this run about "
        f"{hours(remaining):.2f} h"
    )


async def run_rows(
    judge: Any,
    rows: Sequence[Mapping[str, Any]],
    todo: Sequence[int],
    writer: Writer,
    *,
    strategy: str,
    have_facts: bool,
    stop: dict[str, bool],
    stop_file: Path,
) -> int:
    """Judge each row of *todo* in order, one at a time; return the exit code."""
    from omrs.core.answer.judges.base import JudgeUnavailable

    started, failures, last_reason = time.perf_counter(), 0, None
    for count, idx in enumerate(todo, start=1):
        if stop_file.exists():
            say(f"[stop] {stop_file.name} found; stopped after {count - 1} rows")
            return 0
        if stop["flag"]:
            say(f"[stop] signal received; stopped after {count - 1} rows")
            return 0
        try:
            record, call = await judge_one(judge, rows[idx])
        except JudgeUnavailable as unavailable:
            say(f"[error] {unavailable.reason}")
            return EXIT_UNAVAILABLE
        writer.write(record)
        if call is not None and record["error"] is None and not have_facts:
            writer.write(facts_record(strategy, call))
            have_facts = True
        failures = failures + 1 if record["error"] is not None else 0
        last_reason = record["error"] or last_reason
        if failures > MAX_CONSECUTIVE_FAILURES:
            say(
                f"[error] {failures} rows in a row failed (last reason: {last_reason}); "
                "the router looks down. Fix it, then run again with --resume."
            )
            return EXIT_FAILURES
        if count == min(TIMING_ROWS, len(todo)):
            elapsed = time.perf_counter() - started
            say(timing_line(count, elapsed, len(todo) - count, len(rows)))
    say(f"[done] {len(todo)} rows judged")
    return 0


def _install_stop(stop: dict[str, bool]) -> dict[int, Any]:
    """Turn SIGTERM and SIGINT into a stop flag read between rows; return the old handlers."""

    def handler(signum: int, _frame: object) -> None:
        stop["flag"] = True

    return {sig: signal.signal(sig, handler) for sig in (signal.SIGTERM, signal.SIGINT)}


# --- the command -------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategy", required=True, choices=sorted(JUDGES))
    parser.add_argument("--limit", type=int, default=None, help="first N rows of the fixed order")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--gguf-file", default=None, help="GGUF file name in SWEEP_GGUF_DIR")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be 1 or more")
    return args


def dry_run(args: argparse.Namespace, rows: Sequence[Mapping], todo: Sequence[int]) -> None:
    """Print what the run would do; nothing starts and nothing is sent."""
    _model, settings, path = configure(args.strategy, args.out_dir, args.gguf_file,
                                       hash_missing=False)  # fmt: skip
    datasets = sorted({rows[idx]["dataset"] for idx in todo})
    say(f"[dry-run] would judge {len(todo)} rows from {len(datasets)} datasets, one at a time")
    say(json.dumps(settings_summary(args.strategy, settings, path), indent=2))
    say("[dry-run] no router started, no request sent")


def main(argv: Sequence[str] | None = None, *, make_judge: MakeJudge | None = None) -> int:
    """Run the command; return the exit code. *make_judge* replaces the production judge (tests)."""
    args = parse_args(argv)
    try:
        return _main(args, make_judge or production_judge)
    except (RunError, rc.RouterConfigError, lib.ScoreError) as error:
        say(f"[error] {error}")
        return 2


def _main(args: argparse.Namespace, make_judge: MakeJudge) -> int:
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / f"aggrefact-{args.strategy}.jsonl"
    parquet_sha256 = lib.file_sha256(args.parquet)
    if parquet_sha256 != lib.PARQUET_SHA256:
        raise RunError(f"{args.parquet.name} is not the pinned TEST split (SHA-256 differs)")
    rows = lib.load_rows(args.parquet)
    order = lib.row_order(len(rows), lib.SHUFFLE_SEED, args.limit)
    header = make_header(args.strategy, parquet_sha256, args.limit, len(rows))
    done, have_facts = prior_state(results, header, resume=args.resume)
    todo = [idx for idx in order if idx not in done]
    say(f"[run] {args.strategy}: {len(order)} rows queued, {len(done)} done, {len(todo)} to do")
    if args.dry_run:
        dry_run(args, rows, todo)
        return 0
    judge = make_judge(args.strategy, out_dir, args.gguf_file)
    if getattr(judge, "version", header["judge_version"]) != header["judge_version"]:
        raise RunError("the built judge's version differs from OMRS's registry")
    stop = {"flag": False}
    previous = _install_stop(stop)
    writer = Writer(results)
    try:
        if not done and results.stat().st_size == 0:
            writer.write(header)
        return asyncio.run(
            run_rows(judge, rows, todo, writer, strategy=args.strategy, have_facts=have_facts,
                     stop=stop, stop_file=out_dir / "RUNSTOP")
        )  # fmt: skip
    finally:
        writer.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
