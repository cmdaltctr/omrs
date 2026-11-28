"""Experiment 35 stage runner: one dataset, one stage, one setup or index, one repetition.

The command line lives in ``cli35.py`` (``--help`` lists every option). Stages
are named in :data:`STAGE_TABLE`; each is ``async def stage(ctx: stages35.Ctx)
-> int``:

* ``ingest`` and ``seal``: one index into its own store, then its fingerprint
  and the build environment record;
* ``search`` (``search35``): ranked lists of 100 stored chunks, no metric;
* ``answer`` (``answers35``): search, head, assembly and one answer per
  question; refuses without ``selection.json`` (main run);
* ``judge`` (``judges35``): the ``--judges`` claim checks of an answer folder;
* ``ragas`` (``ragas35``): the five Ragas metrics of an answer folder;
* ``closedbook`` (``closedbook35``) and ``oracle`` (``oracle35``): the floor
  and ceiling runs, run 1 only;
* ``determinism`` (``determinism35``): G1 for one answer setup on saved files
  after a passing join; it skips every step below (no settings, router,
  guard, engine or machine line);
* ``claimkinds`` (``claimstage35``): the claim kinds of an answer run folder
  (``--classify-examples``, ``--classify-concurrency``);
* ``lengthcheck`` (``lengthcheck35``): the length-controlled check over the
  whole output folder into ``<out>/lengthcheck`` (``--judges chat,clef_flash``).

The answer, closed-book, oracle, judge, Ragas and claim-kind stages refuse a
main run while half B is locked (``stagekit35.require_half_b_open``).

``--answers closedbook-own|closedbook-rag|oracle`` points the judge and Ragas
stages at those folders. Options of note: ``--answer-concurrency``,
``--chat-concurrency``, ``--ragas-concurrency`` and ``--rate-limit-attempts``
(hosted calls through the gate; defaults in ``arms.CONCURRENCY_DEFAULTS``).

Per process the runner, in this order and before any paid call:

1. writes ``<local>/config/<dataset>-<name>-<stage>/omrs.jsonc``
   (``arms.settings_values``), points ``OMRS_CONFIG_DIR``, ``OMRS_STATE_DIR``
   and ``LANCEDB_URI`` (the index's own store) there, and stops with exit code
   2 when OMRS resolves any written value otherwise (an environment variable or
   ``.env`` entry), or the PDF reader resolves to another reader;
2. selects the questions in frozen order (``--limit`` or ``--qids``);
3. for an ingest, checks the prepared passage folder against ``plan.json``;
4. builds the stage key with the configuration hash, and refuses a
   ``--resume`` with another key before it skips a stage done earlier;
5. checks the machine (GPU and pinned image), the input hashes, starts the
   router, and runs ``guard_run`` with ``check_args=True``, the pre-freeze and
   smoke flags, and the command with every resolved concurrency value;
6. builds the engine, appends the machine line and runs the stage.

``--dry-run`` stops after step 4 and prints the plan: no router, no model, no
request. ``--setup all`` or an index with a search stage runs each unit in its
own process, in table order, and stops at the first non-zero exit code.

Exit codes: 0 done; 2 setup or input error (nothing scored); 3 a check found a
difference; 4 a judge could not start, or a ``chat`` claim call failed (the
message names it; ``--resume`` sends it again); 5 rate-limited past the attempt limit or
out of credit (finished rows kept, no done-marker); 6 items still open (no
done-marker; run again with ``--resume``). Heavy-run rule: tell the operator
before a run without ``--dry-run``.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
for _folder in (PROJECT_ROOT, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import answers35  # noqa: E402
import arms  # noqa: E402
import claimstage35  # noqa: E402
import cli35  # noqa: E402
import closedbook35  # noqa: E402
import datasets35  # noqa: E402
import determinism35  # noqa: E402
import hostedusage35  # noqa: E402
import judges35  # noqa: E402
import lengthcheck35  # noqa: E402
import oracle35  # noqa: E402
import outputs35  # noqa: E402
import ragas35  # noqa: E402
import scoring35  # noqa: E402
import search35  # noqa: E402
import stagekit35  # noqa: E402
import stages35  # noqa: E402
import zai35  # noqa: E402
from experiments._lib import router_env  # noqa: E402
from experiments._lib.hosted_calls import RateLimitStop  # noqa: E402
from experiments._lib.preflight import PreflightError  # noqa: E402
from experiments._lib.trace import TraceWriter  # noqa: E402

from omrs.capabilities import resolve_pdf_reader  # noqa: E402

say = outputs35.say
EXIT_SETUP, EXIT_MISMATCH, EXIT_JUDGE, EXIT_RATE_LIMIT, EXIT_OPEN = 2, 3, 4, 5, 6
#: Not a run blocker: metadata extraction is off, so no classification request is sent.
IGNORED_ROLES = ("classification",)

#: Stage name to stage function. A later stage adds one line here and one line
#: to ``arms.STAGE_KINDS``.
STAGE_TABLE: dict[str, Callable[[stages35.Ctx], Awaitable[int]]] = {
    "ingest": stages35.ingest_stage,
    "seal": stages35.seal_stage,
    "search": search35.search_stage,
    "answer": answers35.answer_stage,
    "judge": judges35.judge_stage,
    "ragas": lambda ctx: ragas35.ragas_stage(ctx, ctx.plan),
    "closedbook": closedbook35.closedbook_stage,
    "oracle": oracle35.oracle_stage,
    "determinism": determinism35.determinism_stage,
    "claimkinds": claimstage35.claimkinds_stage,
    "lengthcheck": lengthcheck35.lengthcheck_stage,
}

SETUP_ERRORS = (
    arms.ArmConfigError,
    zai35.EndpointError,
    datasets35.DatasetError,
    router_env.RouterConfigError,
    PreflightError,
    outputs35.StageFileExistsError,
    outputs35.ResumeMismatchError,
    stages35.StageOrderError,
    stages35.SealRefused,
    stages35.EnvironmentMismatch,
    stagekit35.FingerprintError,
    stagekit35.RerankFailed,
    ragas35.RagasRefused,
    scoring35.HalfBLocked,
    outputs35.NoRunFiles,
    ValueError,
)


def plan_units(kind: str, *, setup: str | None, index: str | None) -> list[tuple[str, str]]:
    """Return the ``(kind, name)`` units one command runs, in table order.

    An index stage runs on index names: ``--index NAME``, the index of
    ``--setup NAME``, or all 9 for ``--setup all``. A search or answer stage
    runs on setup names: ``--setup NAME``, all 72 for ``--setup all``, or the 8
    setups of ``--index NAME``.
    """
    if kind == "lengthcheck":  # one check over the whole output folder
        return [(kind, next(iter(arms.SEARCH_SETUPS)) if setup in (None, "all") else str(setup))]
    if kind == "index":
        if index is not None:
            return [(kind, index)]
        if setup == "all":
            return [(kind, name) for name in arms.INDEXES]
        return [(kind, arms.parse_setup(str(setup)).index)]
    if index is not None:
        return [(kind, s.name) for s in arms.index_setups(index)]
    if setup == "all":
        return [(kind, name) for name in arms.SEARCH_SETUPS]
    return [(kind, str(setup))]


def main(argv: Sequence[str] | None = None, *, deps: Any = None) -> int:
    """Run one command line; return the exit code. *deps* replaces the live world (tests)."""
    argv = list(argv if argv is not None else sys.argv[1:])
    args = cli35.parse_args(argv)
    if deps is None:
        from live35 import LiveDeps

        deps = LiveDeps()
    kind = arms.STAGE_KINDS[args.stage]
    units = plan_units(kind, setup=args.setup, index=args.index)
    if args.stage in ("judge", "ragas"):
        kind = args.answers
    if len(units) > 1:
        return run_all(argv, units, deps)
    from omrs.core.answer.judges.base import JudgeUnavailable

    try:
        return run_one(args, argv, kind, units[0][1], deps)
    except JudgeUnavailable as refused:
        say(f"[error] judge cannot start: {refused.reason}")
        return EXIT_JUDGE
    except judges35.ClaimCallStop as stop:
        say(f"[stop] {stop}")
        return EXIT_JUDGE
    except RateLimitStop as stop:
        say(f"[stop] {stop}; finished rows are kept, no done-marker. Run again with --resume.")
        hostedusage35.record_stop(args, stop)
        return EXIT_RATE_LIMIT
    except stages35.StageIncomplete as open_items:
        say(f"[open] {open_items}")
        return EXIT_OPEN
    except SETUP_ERRORS as error:
        say(f"[error] {error}")
        return EXIT_SETUP


def run_all(argv: list[str], units: Sequence[tuple[str, str]], deps: Any) -> int:
    """Run each unit in its own process, in order; stop at the first non-zero exit code."""
    rest, skip = [], False
    for arg in argv:
        if skip:
            skip = False
        elif arg in ("--setup", "--index"):
            skip = True
        else:
            rest.append(arg)
    for kind, name in units:
        flag = "--index" if kind == "index" else "--setup"
        say(f"[all] {name}")
        code = deps.spawn([*rest, flag, name])
        if code != 0:
            say(f"[all] {name} stopped with exit code {code}; later units not run")
            return code
    return 0


def _layout(args: Any, kind: str) -> outputs35.Layout:
    if kind == "index" and args.index_from is not None:
        raise arms.ArmConfigError(
            "an index stage writes its index; --index-from is only for search and answer stages"
        )
    return outputs35.Layout(
        args.out_dir.absolute(),
        local=args.local_dir.absolute() if args.local_dir else None,
        index_root=args.index_from.absolute() if args.index_from else None,
    )


def _configure(args: Any, setup: arms.Setup, name: str, plan: Any, layout: Any) -> tuple:
    """Write, check and load the scratch settings; return (values, settings, path, judges)."""
    judges = arms.parse_judges(args.judges)
    config_dir = layout.config_dir(args.dataset, name, args.stage)
    extra = {"VECTOR_STORE": "lancedb", "LANCEDB_URI": str(layout.store(setup.index))}
    if "chat" in judges:  # never in omrs.jsonc: the repository is public (zai35)
        extra[zai35.OMRS_ENV] = zai35.base_url(plan)
    router_env.prepare_environment(extra, config_dir=config_dir, state_dir=layout.state_dir)
    values = arms.settings_values(
        setup, plan, router_env.gguf_dir(), answer_host=args.answer_host.strip(), judges=judges
    )
    path = router_env.write_settings(values, config_dir)
    router_env.check_settings_file(config_dir)
    settings = router_env.load_settings()
    router_env.check_resolved(settings, arms.without_keys(values))
    reader = resolve_pdf_reader(settings)
    if reader != values["pdf_reader"]:
        raise arms.ArmConfigError(
            f"pdf_reader resolves to {reader!r} on this machine; the plan pins "
            f"{values['pdf_reader']!r}. Install it, or remove the PDF_READER override."
        )
    return values, settings, path, judges


def _role_problems(settings: Any) -> list[list[str]]:
    from omrs.compose_answer import llamacpp_roles

    problems = llamacpp_roles(settings).problems
    return [list(p) for p in problems if p[0] not in IGNORED_ROLES]


def _concurrency(args: Any) -> dict[str, int]:
    return {name: int(getattr(args, name)) for name in cli35.CONCURRENCY_OPTIONS}


def _command(argv: Sequence[str], args: Any) -> str:
    """Return the command for the run record, with every resolved concurrency value (D7)."""
    flags = [x for n, v in _concurrency(args).items() for x in (f"--{n.replace('_', '-')}", str(v))]
    return shlex.join(["run_arms.py", *argv, *flags])


def _config(plan: Any, values: Mapping[str, Any], commit: str, mode: str) -> dict[str, Any]:
    """Return the configuration fields of the key (task 3.4): settings, runtime, prompts, commit.

    The GGUF entries carry machine paths; the runtime hash covers the models.
    *mode* is the run mode (review R2-01).
    """
    hashed = {k: v for k, v in arms.without_keys(values).items() if k != "llamacpp_models"}
    hashed["recorded_pins"] = arms.recorded_pins(plan)
    return outputs35.config_fields(
        settings=hashed,
        runtime=plan["runtime"],
        prompts=arms.pinned(plan, "pins", "prompts"),
        commit=commit,
        mode=mode,
    )


def _run_mode(args: Any) -> str:
    return "prefreeze" if args.prefreeze else ("smoke" if args.smoke else "main")


def _key_config(args: Any, plan: Any, setup: arms.Setup, values: Any, commit: str) -> dict:
    """Return the key's configuration fields; a stage that reads an index adds ``index_config``.

    The index fields hash the settings of ``<index>-roff-hon`` with no answer host
    and no judge, as the ingest key does (review R2-05). A main run also asks for
    an index built by a main run; other modes leave the index run mode out.
    """
    mode = _run_mode(args)
    index = arms.index_setup(setup.index)
    found = arms.settings_values(index, plan, router_env.gguf_dir(), answer_host="", judges=())
    built = _config(plan, found, commit, mode)
    if args.stage in arms.INDEX_STAGES:
        return built
    if mode != "main":
        built.pop("run_mode")
    return {**_config(plan, values, commit, mode), "index_config": built}


def _ingest_files(args: Any, plan: Any, root: Path, questions: Sequence[Any]) -> list[Path]:
    seed = arms.plan_seed(plan, "smoke_sample")
    if args.dataset == "financebench":
        return datasets35.corpus_files(
            "financebench", root, questions, args.corpus_sample, Path(), seed=seed
        )
    if args.passages_dir is None:
        raise arms.ArmConfigError(f"ingest of {args.dataset} needs --passages-dir (prepare35.py)")
    passages = args.passages_dir.absolute()
    datasets35.check_passages(passages, args.dataset, plan)
    return datasets35.corpus_files(
        args.dataset, root, questions, args.corpus_sample, passages, seed=seed
    )


def _questions(args: Any, plan: Any, root: Path) -> list[Any]:
    return datasets35.select(
        datasets35.load_questions(args.dataset, root),
        args.limit,
        seed=arms.plan_seed(plan, "question_order"),
        qids=args.qids,
    )


def run_saved(args: Any, kind: str, name: str, deps: Any) -> int:
    """Run a stage that reads saved files only: no settings, router, guard, engine or machine."""
    plan = deps.plan()
    questions = _questions(args, plan, datasets35.data_root())
    ctx = stages35.Ctx(
        dataset=args.dataset,
        setup=name,
        kind=kind,
        run=args.run,
        questions=questions,
        layout=_layout(args, kind),
        key={},
        resume=args.resume,
        trace=None,  # type: ignore[arg-type]
        plan=plan,
        args=args,
    )
    code = asyncio.run(STAGE_TABLE[args.stage](ctx))
    say(f"[{args.stage}] {args.dataset}/{name}: exit {code}")
    return code


def run_one(args: Any, argv: Sequence[str], kind: str, name: str, deps: Any) -> int:
    """Run one stage of one setup or index; return its exit code."""
    if args.stage in arms.SAVED_FILE_STAGES:
        return run_saved(args, kind, name, deps)
    plan = deps.plan()
    setup = arms.index_setup(name) if kind == "index" else arms.parse_setup(name)
    layout = _layout(args, kind)
    values, settings, path, judges = _configure(args, setup, name, plan, layout)
    problems = _role_problems(settings)
    root = datasets35.data_root()
    questions = _questions(args, plan, root)
    files = _ingest_files(args, plan, root, questions) if args.stage == "ingest" else []
    key = outputs35.run_key(
        args.limit,
        args.corpus_sample,
        arms.plan_seed(plan, "question_order"),
        [q.qid for q in questions],
        config=_key_config(args, plan, setup, values, deps.commit()),
    )
    folder = layout.stage_dir(args.dataset, kind, name, args.run)
    if args.resume and (folder / f".done-{args.stage}.json").exists():
        outputs35.check_stage_key(folder, args.stage, key)
        say(f"[{args.stage}] {args.dataset}/{name}/run{args.run}: done earlier, skipped")
        return 0
    if (folder / f"{args.stage}.key.json").exists() and not args.resume and not args.dry_run:
        raise outputs35.StageFileExistsError(
            f"{args.stage} started earlier in {folder}; pass --resume, or use another --out-dir"
        )
    roles = arms.stage_roles(setup, args.stage, judges)
    if args.dry_run:
        return cli35.print_plan(
            args,
            setup,
            name,
            path,
            layout,
            roles,
            questions,
            problems,
            concurrency=_concurrency(args),
            resolved=cli35.resolved(settings),
        )
    if problems:
        raise arms.ArmConfigError(f"OMRS lists router role problems: {problems}")
    _require_keys(args.stage, judges)
    if not deps.chunking_token_aware(settings):
        raise arms.ArmConfigError(
            f"{name}: OMRS does not resolve the model-token-aware Markdown path "
            "(is the tokenizer revision cached on this machine?)"
        )
    machine = deps.machine()
    stages35.check_machine(machine, plan)
    deps.verify_inputs(root, args.dataset, files, plan)
    models = [arms.plan_role(plan, role) for role in roles]
    block = {**plan["runtime"], "models": models}
    deps.start_router([m["file"] for m in models], {"runtime": {"models": models}})
    base_url = str(settings.llamacpp_router_url).rstrip("/").removesuffix("/v1")
    found = deps.guard(
        block,
        base_url=base_url,
        command=_command(argv, args),
        prefreeze=args.prefreeze,
        smoke=args.smoke,
    )
    environment = stages35.environment_record(machine, found)
    trace = _trace(args, name, plan, settings, models, folder)
    engine = deps.engine()
    try:
        ctx = stages35.Ctx(
            dataset=args.dataset,
            setup=name,
            kind=kind,
            run=args.run,
            questions=questions,
            layout=layout,
            key=key,
            resume=args.resume,
            trace=trace,
            engine=engine,
            settings=settings,
            plan=plan,
            args=args,
            files=files,
            environment=environment,
            redact=engine.redact,
        )
        ctx.judge = lambda judge: deps.judge(judge, settings, plan)
        ctx.router = getattr(deps, "router", None)
        ctx.runtime_check = getattr(deps, "runtime_check", None)
        stages35.record_machine(ctx, machine, environment)
        code = asyncio.run(STAGE_TABLE[args.stage](ctx))
    finally:
        engine.close()
    say(f"[{args.stage}] {args.dataset}/{name}/run{args.run}: exit {code}")
    return code


def _require_keys(stage: str, judges: Sequence[str]) -> None:
    hosted = ("answer", "closedbook", "oracle", "claimkinds")
    needed = ["OPENROUTER_API_KEY"] if stage in hosted else []
    needed += [arms.GLM_KEY_ENV] if "chat" in judges else []
    missing = [n for n in needed if not os.environ.get(n)]
    if missing:
        raise arms.ArmConfigError(f"set {', '.join(missing)} before this stage (never in a file)")


def _trace(args: Any, name: str, plan: Any, settings: Any, models: Any, folder: Path) -> Any:
    smoke = "/smoke" if args.smoke else ""
    identities: dict[str, Any] = {
        m["role"]: {"file": m["file"], "sha256": m["sha256"]} for m in models
    }
    identities["answer"] = {
        "model": arms.ANSWER_MODEL,
        "allowed_hosts": settings.answer.allowed_hosts,
    }
    setup = arms.index_setup(name) if args.stage in arms.INDEX_STAGES else arms.parse_setup(name)
    return TraceWriter(
        folder / "traces.jsonl",
        benchmark_revision=f"exp35-protocol-{plan.get('protocol_version')}",
        run_id=f"{args.dataset}/{name}/run{args.run}{smoke}",
        arm=name,
        repetition=args.run,
        effective_settings={
            "setup": name,
            "stage": args.stage,
            "rerank": setup.rerank,
            "hybrid": setup.hybrid_on,
            "top_k": arms.TOP_K,
            "prefreeze": args.prefreeze,
            **_concurrency(args),
            **cli35.resolved(settings),
            "recorded_pins": arms.recorded_pins(plan),
        },
        model_identities=identities,
    )


if __name__ == "__main__":
    sys.exit(main())
