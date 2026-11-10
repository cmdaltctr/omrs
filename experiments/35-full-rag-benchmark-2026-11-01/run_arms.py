"""Experiment 35 arm runner: one dataset, one arm (or all), one stage, one repetition.

Stages (design D4, D5):

* ``ingest``       build the arm's index, one file at a time. The reranker-off
                   and hybrid arms search the baseline index and skip this.
* ``search``       top-10 search per question; IDs, scores and the primary
                   metrics (Recall@10, MRR@10, nDCG@10, hit@page).
* ``answer``       one hosted answer per question (claim checks off), then
                   each ``--judges`` strategy judges every cited claim.
* ``determinism``  compare runs 1 to 3 of the arm (IDs, answers, verdicts).

Settings: each process writes ``<out>/config/<dataset>-<arm>-<stage>/omrs.jsonc``
(``arms.settings_values``), points ``OMRS_CONFIG_DIR`` and ``OMRS_STATE_DIR``
there, and OMRS's managed router serves the plan's GGUF files from
``SWEEP_GGUF_DIR``. ``EXP35_DATA_DIR`` names the dataset folder. Keys come only
from ``OPENROUTER_API_KEY`` and ``OMRS_EXP35_ZAI_KEY`` through ``env://``
references; no key is printed.

``--dry-run`` writes and loads the scratch settings, prints the plan and exits:
no router, no model, no request. ``--arm all`` runs each arm in table order in
its own process and stops at the first failure.

Exit codes: 0 done; 2 setup or input error (nothing scored); 3 the determinism
check found a difference; 4 a judge could not start.
Heavy-run rule: tell the operator before a run without ``--dry-run``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
for _folder in (PROJECT_ROOT, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
import datasets35  # noqa: E402
import outputs35  # noqa: E402
import stages35  # noqa: E402
from experiments._lib import router_env  # noqa: E402
from experiments._lib.preflight import PreflightError  # noqa: E402
from experiments._lib.trace import TraceWriter  # noqa: E402

say = outputs35.say
DEFAULT_OUT = EXP_DIR / "output" / "restricted" / "runs"
SMOKE_OUT = EXP_DIR / "output" / "restricted" / "smoke"
EXIT_SETUP, EXIT_MISMATCH, EXIT_JUDGE = 2, 3, 4
#: Not a run blocker: metadata extraction is off, so no classification request is sent,
#: and the router refuses an unlisted model per request only.
IGNORED_ROLES = ("classification",)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Return the checked command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, choices=datasets35.DATASETS)
    parser.add_argument("--arm", required=True, choices=[*arms.ARMS, "all"])
    parser.add_argument("--stage", required=True, choices=arms.STAGES)
    parser.add_argument("--run", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--limit", type=int, help="first N questions of the frozen order")
    parser.add_argument(
        "--corpus-sample", type=int, help="ingest gold documents plus N seeded others (smoke)"
    )
    parser.add_argument("--judges", default="", help="comma list: clef_flash,granite_guardian,chat")
    parser.add_argument("--answer-host", default="", help="the one OpenRouter host for answers")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be 1 or more")
    if args.corpus_sample is not None and args.corpus_sample < 0:
        parser.error("--corpus-sample must be 0 or more")
    # A question limit or a sampled corpus both make a smoke run: never a run record.
    args.smoke = args.limit is not None or args.corpus_sample is not None
    if args.out_dir is None:
        args.out_dir = SMOKE_OUT if args.smoke else DEFAULT_OUT
    return args


def main(argv: Sequence[str] | None = None, *, deps: Any = None) -> int:
    """Run the command line; return the exit code. *deps* replaces the live world (tests)."""
    args = parse_args(argv)
    if deps is None:
        from live35 import LiveDeps

        deps = LiveDeps()
    if args.arm == "all":
        return run_all(list(argv if argv is not None else sys.argv[1:]), deps)
    from omrs.core.answer.judges.base import JudgeUnavailable

    try:
        return run_one(args, deps)
    except JudgeUnavailable as refused:
        say(f"[error] a judge cannot start: {refused.reason}")
        return EXIT_JUDGE
    except (
        arms.ArmConfigError,
        datasets35.DatasetError,
        router_env.RouterConfigError,
        PreflightError,
        outputs35.StageFileExistsError,
        outputs35.ResumeMismatchError,
        stages35.StageOrderError,
        ValueError,
    ) as error:
        say(f"[error] {error}")
        return EXIT_SETUP


def run_all(argv: list[str], deps: Any) -> int:
    """Run each arm in table order, one process each; stop at the first failure."""
    at = argv.index("--arm")
    for name in arms.ARMS:
        child = [*argv[:at], "--arm", name, *argv[at + 2 :]]
        say(f"[all] {name}")
        code = deps.spawn(child)
        if code != 0:
            say(f"[all] {name} stopped with exit code {code}; later arms not run")
            return code
    return 0


def _stage_folder(layout: outputs35.Layout, args: argparse.Namespace, arm: arms.Arm) -> Path:
    if args.stage == "ingest":
        return layout.index_dir(args.dataset, arm.name)
    return layout.run_dir(args.dataset, arm.name, args.run)


def _stage_done(layout: outputs35.Layout, args: argparse.Namespace, arm: arms.Arm) -> bool:
    folder = _stage_folder(layout, args, arm)
    names = [args.stage] + [f"judge-{j}" for j in arms.parse_judges(args.judges)]
    return all((folder / f".done-{name}.json").exists() for name in names)


def _configure(args: argparse.Namespace, arm: arms.Arm, plan: Any, layout: Any) -> tuple:
    """Write, check and load the scratch settings; return (values, settings, path, judges)."""
    judges = arms.parse_judges(args.judges) if args.stage == "answer" else ()
    if args.stage == "answer" and not args.answer_host.strip():
        raise arms.ArmConfigError("the answer stage needs --answer-host (one OpenRouter host)")
    config_dir = layout.config_dir(args.dataset, arm.name, args.stage)
    extra = {"VECTOR_STORE": "lancedb", "LANCEDB_URI": str(layout.lancedb)}
    router_env.prepare_environment(
        {**extra, **arms.env_overrides(arm)}, config_dir=config_dir, state_dir=layout.state_dir
    )
    values = arms.settings_values(
        arm, plan, router_env.gguf_dir(), answer_host=args.answer_host.strip(), judges=judges
    )
    path = router_env.write_settings(values, config_dir)
    router_env.check_settings_file(config_dir)
    settings = router_env.load_settings()
    router_env.check_resolved(settings, arms.without_keys(values))
    return values, settings, path, judges


def _role_problems(settings: Any) -> list[list[str]]:
    from omrs.compose_answer import llamacpp_roles

    problems = llamacpp_roles(settings).problems
    return [list(p) for p in problems if p[0] not in IGNORED_ROLES]


def _resolved(settings: Any) -> dict[str, Any]:
    answer = settings.answer
    return {
        "embed_model": settings.llamacpp_embed_model,
        "router_url": settings.llamacpp_router_url,
        "router_models_max": settings.llamacpp_router_models_max,
        "rag_profile": settings.rag_profile,
        "tokenizer_model": settings.embedding.tokenizer_model,
        "tokenizer_revision": settings.embedding.tokenizer_revision,
        "metadata_extraction": settings.metadata.extraction_mode,
        "answer_provider": answer.provider,
        "answer_model": answer.model,
        "answer_temperature": answer.temperature,
        "answer_seed": answer.seed,
        "answer_allowed_hosts": answer.allowed_hosts,
        "verify_claims": answer.verify_claims,
    }


def run_one(args: argparse.Namespace, deps: Any) -> int:
    """Run one stage of one arm; return the exit code."""
    arm = arms.ARMS[args.arm]
    layout = outputs35.Layout(args.out_dir)
    if args.stage == "determinism":
        report = stages35.determinism_stage(layout, args.dataset, arm.name)
        parts = [
            report["retrieval"],
            report["answers"] or {"ok": True},
            *report["verdicts"].values(),
        ]
        return 0 if all(part["ok"] for part in parts) else EXIT_MISMATCH
    if args.stage == "ingest" and not arm.owns_index:
        say(f"[ingest] {arm.name} searches the {arm.index_of} index; nothing to ingest")
        return 0
    if args.resume and _stage_done(layout, args, arm):
        say(f"[{args.stage}] {args.dataset}/{arm.name}/run{args.run}: done earlier, skipped")
        return 0
    started = _stage_folder(layout, args, arm) / f"{args.stage}.key.json"
    if started.exists() and not args.resume and not args.dry_run:
        raise outputs35.StageFileExistsError(
            f"{args.stage} started earlier in {started.parent}; "
            "pass --resume, or use another --out-dir"
        )
    if args.stage != "ingest" and not args.dry_run:
        marker = layout.index_dir(args.dataset, arm.index_of) / ".done-ingest.json"
        if not marker.exists():
            raise stages35.StageOrderError(f"the {arm.index_of} index is not built: no {marker}")
    plan = deps.plan()
    values, settings, path, judges = _configure(args, arm, plan, layout)
    root = datasets35.data_root()
    questions = datasets35.select(
        datasets35.load_questions(args.dataset, root), args.limit, seed=arms.SEED
    )
    roles = arms.stage_roles(arm, args.stage, judges)
    problems = _role_problems(settings)
    if args.dry_run:
        return _print_plan(args, arm, settings, path, roles, judges, questions, problems, deps)
    if problems:
        raise arms.ArmConfigError(f"OMRS lists router role problems: {problems}")
    _require_keys(args.stage, judges)
    if args.stage == "ingest" and deps.chunking_token_aware(settings) != arm.token_aware:
        raise arms.ArmConfigError(
            f"{arm.name} needs token-aware chunking {arm.token_aware}; OMRS resolved the other "
            "path (is the tokenizer revision cached on this machine?)"
        )
    key = outputs35.run_key(args.limit, args.corpus_sample, arms.SEED, [q.qid for q in questions])
    files = (
        datasets35.corpus_files(
            args.dataset, root, questions, args.corpus_sample, layout.work_dir, seed=arms.SEED
        )
        if args.stage == "ingest"
        else []
    )
    deps.verify_inputs(root, args.dataset, files)
    models = [arms.plan_role(plan, role) for role in roles]
    deps.start_router([models[0]["file"]], {"runtime": {"models": models}})
    block = {**plan["runtime"], "models": models}
    base_url = str(settings.llamacpp_router_url).rstrip("/").removesuffix("/v1")
    runtime_path = (
        layout.root / "runtime" / f"{args.dataset}-{arm.name}-{args.stage}-run{args.run}.json"
    )
    deps.guard(block, base_url=base_url, smoke=args.smoke, runtime_path=runtime_path)
    return asyncio.run(
        _run_stage(args, arm, plan, settings, models, judges, questions, key, files, layout, deps)
    )


def _require_keys(stage: str, judges: Sequence[str]) -> None:
    needed = ["OPENROUTER_API_KEY"] if stage == "answer" else []
    needed += [arms.GLM_KEY_ENV] if "chat" in judges else []
    missing = [name for name in needed if not os.environ.get(name)]
    if missing:
        raise arms.ArmConfigError(f"set {', '.join(missing)} before this stage (never in a file)")


def _trace(args: Any, arm: arms.Arm, plan: Any, settings: Any, models: Any, layout: Any) -> Any:
    folder = _stage_folder(layout, args, arm)
    smoke = f"/limit{args.limit}" if args.limit is not None else ""
    identities: dict[str, Any] = {
        m["role"]: {"file": m["file"], "sha256": m["sha256"]} for m in models
    }
    identities["answer"] = {
        "model": arms.ANSWER_MODEL,
        "allowed_hosts": settings.answer.allowed_hosts,
    }
    return TraceWriter(
        folder / "traces.jsonl",
        benchmark_revision=f"exp35-protocol-{plan.get('protocol_version')}",
        run_id=f"{args.dataset}/{arm.name}/run{args.run}{smoke}",
        arm=arm.name,
        repetition=args.run,
        effective_settings={
            "arm": arm.name,
            **arms.search_kwargs(arm),
            "top_k": arms.TOP_K,
            "token_aware": arm.token_aware,
            **_resolved(settings),
        },
        model_identities=identities,
    )


async def _run_stage(
    args: Any,
    arm: arms.Arm,
    plan: Any,
    settings: Any,
    models: Any,
    judges: Sequence[str],
    questions: list[Any],
    key: Any,
    files: list[Path],
    layout: Any,
    deps: Any,
) -> int:
    from omrs.core.answer.verify import verify_claims

    engine = deps.engine()
    try:
        ctx = stages35.Ctx(
            args.dataset,
            arm,
            args.run,
            questions,
            layout,
            key,
            args.resume,
            _trace(args, arm, plan, settings, models, layout),
            engine.redact,
        )
        collection = arms.collection(args.dataset, arm)
        call = {"top_k": arms.TOP_K, "collection_name": collection, **arms.search_kwargs(arm)}
        if args.stage == "ingest":
            await stages35.ingest_stage(
                ctx, files, lambda path: engine.ingest(str(path), collection_name=collection)
            )
        elif args.stage == "search":
            id_map = (
                datasets35.freshstack_id_map(datasets35.data_root())
                if args.dataset == "freshstack"
                else {}
            )
            stages35.search_stage(ctx, lambda text: engine.search(text, **call), id_map)
        else:
            await stages35.answer_stage(ctx, lambda text: engine.answer(text, **call))
            for name in judges:
                judge = deps.judge(name, settings, plan)
                await stages35.judge_stage(ctx, name, judge, verify_claims)
    finally:
        engine.close()
    say(f"[{args.stage}] {args.dataset}/{arm.name}/run{args.run}: complete")
    return 0


def _print_plan(
    args: Any,
    arm: arms.Arm,
    settings: Any,
    path: Path,
    roles: Sequence[str],
    judges: Sequence[str],
    questions: Sequence[Any],
    problems: list,
    deps: Any,
) -> int:
    plan = {
        "nothing_started": True,
        "settings_file": str(path),
        "out_dir": str(args.out_dir),
        "dataset": args.dataset,
        "arm": arm.name,
        "stage": args.stage,
        "run": args.run,
        "collection": arms.collection(args.dataset, arm),
        "index_of": arm.index_of,
        "search": arms.search_kwargs(arm),
        "token_aware": arm.token_aware,
        "models": list(roles),
        "judges": list(judges),
        "corpus_sample": args.corpus_sample,
        "questions": [q.qid for q in questions],
        "keys_set": {n: bool(os.environ.get(n)) for n in ("OPENROUTER_API_KEY", arms.GLM_KEY_ENV)},
        "resolved": _resolved(settings),
        "role_problems": problems,
    }
    say("[dry-run] nothing started, nothing sent")
    say(json.dumps(plan, indent=2, default=str))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
