"""Experiment 35 stage runner (``run_arms.py``, ``cli35.py``) with stub router, guard and engine.

Rules under test: the parser (tasks 4.1, 13.2); setup planning; the settings
check before any call (tasks 4.6, 13.1, 13.1a); the guard command and run
flags (tasks 4.1, 5.3, 5.7); resume and the configuration hash (task 3.4);
``--local-dir`` and ``--index-from`` (tasks 5.1, 5.2); the passage tree check
(task 5.4c); the machine record (task 5.6); exit codes 5 and 6.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from experiments._lib.hosted_calls import RateLimitStop
from experiments._lib.preflight import PreflightError
from tests._exp35_fixtures import fake_plan, load, make_data_root, make_gguf, unpin

arms = load("arms")
cli35 = load("cli35")
datasets35 = load("datasets35")
outputs35 = load("outputs35")
prepare35 = load("prepare35")
run_arms = load("run_arms")

MACHINE = {"host": "h", "pod_id": None, "gpu": "G", "image": "img@sha256:" + "1" * 64}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Path]:
    """Point the runner at tmp data and GGUF folders; restore the environment after."""
    saved = dict(os.environ)
    os.environ["EXP35_DATA_DIR"] = str(make_data_root(tmp_path / "DATA"))
    os.environ["SWEEP_GGUF_DIR"] = str(make_gguf(tmp_path / "gguf"))
    # conftest provider defaults would override the scratch file (the runner stops on that).
    for name in (
        "EMBED_PROVIDER",
        "LOCAL_BACKEND",
        "EMBEDDING__TOKENIZER_MODEL",
        "EMBEDDING__TOKENIZER_REVISION",
        "PDF_READER",
    ):
        os.environ.pop(name, None)
    try:
        yield tmp_path
    finally:
        os.environ.clear()
        os.environ.update(saved)


class _Engine:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def ingest(self, path: str, *, collection_name: str) -> dict[str, Any]:
        self.log.append(f"ingest {path} -> {collection_name}")
        return {"status": "ok", "file_details": [{"file": Path(path).name, "chunks": 2}]}

    def redact(self, text: str) -> str:
        return text

    def close(self) -> None:
        self.log.append("close")


class Stub:
    """Records every call to the outside world; can refuse the guard."""

    def __init__(self, *, guard_error: str = "", plan: Any = None) -> None:
        self.log: list[str] = []
        self.guard_error = guard_error
        self.guards: list[dict[str, Any]] = []
        self._plan = plan or _plan_with_tree()

    def plan(self) -> dict[str, Any]:
        return self._plan

    def commit(self) -> str:
        return "c0ffee"

    def verify_inputs(self, root: Path, dataset: str, files: Sequence[Path], plan: Any) -> None:
        self.log.append(f"verify_inputs {dataset}")

    def chunking_token_aware(self, settings: Any) -> bool:
        return bool(settings.embedding.tokenizer_model)

    def start_router(self, files: Sequence[str], plan: Any) -> None:
        self.log.append(f"start_router {list(files)}")

    def guard(self, block: Any, **kwargs: Any) -> Any:
        self.log.append(f"guard {[m['file'] for m in block['models']]}")
        self.guards.append(kwargs)
        if self.guard_error:
            raise PreflightError(self.guard_error)
        return SimpleNamespace(build=11941, models=[{"file": "f.gguf", "sha256": "a" * 64}])

    def machine(self) -> dict[str, Any]:
        return dict(MACHINE)

    def engine(self) -> _Engine:
        self.log.append("engine")
        return _Engine(self.log)

    def spawn(self, argv: Sequence[str]) -> int:
        self.log.append("spawn " + " ".join(argv))
        return 0


def _plan_with_tree(trees: dict[str, str] | None = None) -> dict[str, Any]:
    plan = fake_plan()
    for dataset, tree in (trees or {}).items():
        plan["pins"]["datasets"].setdefault(dataset, {})["passages_tree_sha256"] = tree
    return plan


def _prepared(env: Path, stub: Stub, dataset: str = "bioasq") -> Path:
    passages = env / "passages"
    folder = prepare35.prepare(dataset, env / "DATA", passages, plan=fake_plan())
    stub._plan["pins"]["datasets"].setdefault(dataset, {})["passages_tree_sha256"] = (
        datasets35.verify_tree(folder)
    )
    return passages


def _main(stub: Stub, out: Path, *args: str) -> int:
    return run_arms.main([*args, "--out-dir", str(out)], deps=stub)


def _files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def _ingest_args(passages: Path, *extra: str) -> tuple[str, ...]:
    return (
        "--dataset",
        "bioasq",
        "--index",
        "e4b-c1024",
        "--stage",
        "ingest",
        "--passages-dir",
        str(passages),
        *extra,
    )


# --- parser (tasks 4.1, 13.2) --------------------------------------------------------------


def test_run_arms_holds_no_parser() -> None:
    assert "argparse" not in Path(run_arms.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_concurrency_below_one_is_refused(value: str) -> None:
    with pytest.raises(SystemExit) as stop:
        cli35.parse_args(
            [
                "--dataset",
                "bioasq",
                "--index",
                "e4b-c512",
                "--stage",
                "ingest",
                "--answer-concurrency",
                value,
            ]
        )
    assert stop.value.code == 2


def test_concurrency_defaults_and_overrides_resolve() -> None:
    args = cli35.parse_args(
        [
            "--dataset",
            "bioasq",
            "--index",
            "e4b-c512",
            "--stage",
            "ingest",
            "--chat-concurrency",
            "1",
        ]
    )
    assert (args.answer_concurrency, args.chat_concurrency, args.ragas_concurrency) == (16, 1, 16)
    assert (args.classify_concurrency, args.rate_limit_attempts) == (16, 6)


@pytest.mark.parametrize("flag", ["--setup", "--index"])
def test_an_unknown_name_exits_with_code_2(flag: str) -> None:
    with pytest.raises(SystemExit) as stop:
        cli35.parse_args(["--dataset", "bioasq", flag, "e5b-c512", "--stage", "ingest"])
    assert stop.value.code == 2


def test_a_named_question_run_is_a_smoke_run_in_the_smoke_folder() -> None:
    args = cli35.parse_args(
        [
            "--dataset",
            "freshstack",
            "--setup",
            "e4b-c512-roff-hoff",
            "--stage",
            "ingest",
            "--qids",
            "77536364,77762811",
        ]
    )
    assert args.qids == ["77536364", "77762811"]
    assert args.smoke is True
    assert args.out_dir == cli35.SMOKE_OUT


def test_help_lists_the_new_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli35.parse_args(["--help"])
    text = capsys.readouterr().out
    for option in (
        "--setup",
        "--index",
        "--prefreeze",
        "--rate-limit-attempts",
        "--qids",
        "--local-dir",
        "--index-from",
        "--passages-dir",
        "--answer-concurrency",
    ):
        assert option in text


# --- planning ------------------------------------------------------------------------------


def test_setup_all_plans_72_search_setups_in_table_order() -> None:
    units = run_arms.plan_units("search", setup="all", index=None)
    assert [name for _, name in units] == list(arms.SEARCH_SETUPS)
    assert {kind for kind, _ in units} == {"search"}


def test_an_index_with_a_search_stage_plans_its_8_setups() -> None:
    units = run_arms.plan_units("search", setup=None, index="e4b-c1024")
    assert len(units) == 8 and all(name.startswith("e4b-c1024-") for _, name in units)


def test_an_index_stage_plans_one_ingest_per_dataset_and_a_setup_names_its_index() -> None:
    assert run_arms.plan_units("index", setup=None, index="e4b-c1024") == [("index", "e4b-c1024")]
    assert run_arms.plan_units("index", setup="e4b-c1024-roff-hoff", index=None) == [
        ("index", "e4b-c1024")
    ]
    assert len(run_arms.plan_units("index", setup="all", index=None)) == 9


def test_setup_all_spawns_each_index_in_order_and_stops_at_the_first_failure(env: Path) -> None:
    stub = Stub()
    codes = iter([0, 5, 0])
    stub.spawn = lambda argv: (stub.log.append(" ".join(argv)), next(codes))[1]  # type: ignore[method-assign]
    code = run_arms.main(["--dataset", "bioasq", "--setup", "all", "--stage", "ingest"], deps=stub)
    assert code == 5
    assert [line.split("--index ")[1] for line in stub.log] == list(arms.INDEXES[:2])
    assert all("--setup" not in line for line in stub.log)


# --- settings check before any call (tasks 4.6, 13.1, 13.1a) -----------------------------


def test_dry_run_prints_the_resolved_values_and_starts_nothing(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = Stub()
    os.environ["OPENROUTER_API_KEY"] = "sentinel-value-0451"
    passages = _prepared(env, stub)
    code = _main(
        stub,
        env / "out",
        *_ingest_args(passages, "--limit", "2", "--dry-run", "--chat-concurrency", "3"),
    )
    assert code == 0
    assert stub.log == []
    printed = capsys.readouterr().out
    plan = json.loads(printed[printed.index("{") :])
    assert plan["nothing_started"] is True
    assert plan["collection"] == "exp35_bioasq_e4b_c1024"
    assert plan["store"].endswith("stores/e4b-c1024/lancedb")
    assert plan["concurrency"]["chat_concurrency"] == 3
    assert plan["resolved"]["chunk_overlap"] == 154
    assert plan["resolved"]["hybrid_sparse_backend"] == "bm25"
    assert plan["resolved"]["pdf_reader"] == "pdf_inspector"
    assert "sentinel-value-0451" not in printed and "env://" not in printed


@pytest.mark.parametrize(
    ("variable", "value", "named"),
    [
        ("CHUNKING__CHUNK_SIZE", "300", "chunking.chunk_size"),
        ("CHUNKING__MARKDOWN_CHUNK_SIZE", "300", "chunking.markdown_chunk_size"),
        ("RETRIEVAL__HYBRID_SPARSE_BACKEND", "native", "retrieval.hybrid_sparse_backend"),
        ("PDF_READER", "pypdf", "pdf_reader"),
    ],
)
def test_an_environment_override_stops_before_any_call_and_names_the_setting(
    env: Path, capsys: pytest.CaptureFixture[str], variable: str, value: str, named: str
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    os.environ[variable] = value
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert stub.log == []
    assert named in capsys.readouterr().out


def test_a_pdf_reader_that_resolves_to_another_reader_is_refused(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    monkeypatch.setattr(run_arms, "resolve_pdf_reader", lambda settings: "pypdf")
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert "pdf_reader" in capsys.readouterr().out


def test_no_token_aware_chunking_stops_before_the_router_engine_or_ingest(
    env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pod without the tokenizer cached must stop, not fall back to the legacy splitter.
    stub = Stub()
    passages = _prepared(env, stub)
    asked: list[Any] = []
    monkeypatch.setattr(stub, "chunking_token_aware", lambda settings: asked.append(1) or False)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert asked == [1]
    assert stub.log == []
    assert "model-token-aware Markdown path" in capsys.readouterr().out


# --- an ingest end to end with the stub world -------------------------------------------


def test_ingest_writes_the_index_store_marker_trace_and_machine_line(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    out = env / "out"
    assert _main(stub, out, *_ingest_args(passages, "--prefreeze")) == 0
    assert os.environ["LANCEDB_URI"] == str(out / "stores" / "e4b-c1024" / "lancedb")
    folder = out / "bioasq" / "e4b-c1024"
    assert (folder / ".done-ingest.json").exists()
    assert stub.log.index("guard ['Qwen3-Embedding-4B-Q8_0.gguf']") < stub.log.index("engine")
    trace = json.loads((folder / "traces.jsonl").read_text().splitlines()[0])
    settings = trace["effective_settings"]
    assert settings["rate_limit_attempts"] == 6
    assert settings["hybrid_sparse_backend"] == "bm25"
    pins = settings["recorded_pins"]
    assert pins["reranker_instruction"].startswith("Given a web search query")
    assert pins["hybrid"]["fusion_depth"] == 100
    assert settings["query_instruction"] == ""
    assert settings["hybrid_rrf_k"] == 60
    machine = json.loads((folder / "machine.jsonl").read_text())
    assert machine["environment"]["gpu"] == "G"


def test_the_guard_gets_check_args_flags_and_every_resolved_value(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert (
        _main(stub, env / "out", *_ingest_args(passages, "--prefreeze", "--ragas-concurrency", "9"))
        == 0
    )
    (call,) = stub.guards
    assert call["prefreeze"] is True and call["smoke"] is False
    command = shlex.split(call["command"])
    for name, value in {**arms.CONCURRENCY_DEFAULTS, "ragas_concurrency": 9}.items():
        flag = f"--{name.replace('_', '-')}"
        assert command[len(command) - 1 - command[::-1].index(flag) + 1] == str(value)


def test_a_named_question_run_passes_smoke_and_refuses_an_unknown_id(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages, "--qids", "101,103")) == 0
    assert stub.guards[0]["smoke"] is True
    again = Stub()
    _prepared(env, again)
    assert _main(again, env / "o2", *_ingest_args(passages, "--qids", "101,999")) == 2
    assert again.log == []


def test_a_wrong_gguf_hash_stops_before_any_stage_file_or_engine(env: Path) -> None:
    stub = Stub(guard_error="the SHA-256 of Qwen3-Embedding-4B-Q8_0.gguf differs from the plan")
    passages = _prepared(env, stub)
    out = env / "out"
    assert _main(stub, out, *_ingest_args(passages)) == 2
    assert "engine" not in stub.log
    assert not any(name.endswith(".jsonl") for name in _files(out))


def test_two_output_folders_ingest_the_same_absolute_passage_paths(env: Path) -> None:
    first, second = Stub(), Stub()
    passages = _prepared(env, first)
    _prepared(env, second)
    assert _main(first, env / "a", *_ingest_args(passages)) == 0
    assert _main(second, env / "b", *_ingest_args(passages)) == 0
    paths = [[x for x in s.log if x.startswith("ingest")] for s in (first, second)]
    assert paths[0] == paths[1] and len(paths[0]) == 12


def test_a_changed_passage_file_is_refused_before_any_ingest(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    (passages / "bioasq" / "1005.md").write_text("edited\n", encoding="utf-8")
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert not [x for x in stub.log if x.startswith("ingest")]
    assert "1005.md" in capsys.readouterr().out


def test_a_tree_hash_that_differs_from_the_plan_is_refused(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    stub._plan["pins"]["datasets"]["bioasq"]["passages_tree_sha256"] = "0" * 64
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert stub.log == []


@pytest.mark.parametrize(
    ("key", "task"),
    [
        ("pins.prompts", "P13"),
        ("pins.recorded.hybrid", "P11"),
        ("pins.settings.answer.reasoning", "P10"),
        ("seeds.question_order", "P10"),
    ],
)
def test_a_null_pin_stops_the_runner_with_code_2_before_any_call_and_names_the_key(
    env: Path, capsys: pytest.CaptureFixture[str], key: str, task: str
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    unpin(stub._plan, key, task)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert stub.log == []
    assert not (env / "out").exists() or not list((env / "out").rglob("*.jsonl"))
    out = capsys.readouterr().out
    assert key in out and task in out


def test_a_missing_prompts_table_is_not_read_as_an_empty_one(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    del stub._plan["pins"]["prompts"]
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2
    assert stub.log == []


# --- resume and the configuration hash (task 3.4) ----------------------------------------


def test_resume_skips_a_finished_stage_before_the_router(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 0
    again = Stub()
    _prepared(env, again)
    assert _main(again, env / "out", *_ingest_args(passages, "--resume")) == 0
    assert again.log == []


def test_resume_of_a_finished_stage_with_another_setting_is_refused(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 0
    again = Stub()
    _prepared(env, again)
    again._plan["pins"]["settings"]["retrieval"]["hybrid_rrf_k"] = 30
    assert _main(again, env / "out", *_ingest_args(passages, "--resume")) == 2
    assert again.log == []
    assert "settings_sha256" in capsys.readouterr().out


def test_a_second_run_without_resume_is_refused(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 0
    assert _main(stub, env / "out", *_ingest_args(passages)) == 2


# --- folders (tasks 5.1, 5.2) ------------------------------------------------------------


def test_local_dir_keeps_config_and_state_out_of_the_output_folder(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    out, local = env / "out", env / "local"
    assert _main(stub, out, *_ingest_args(passages, "--local-dir", str(local))) == 0
    assert not (out / "config").exists() and not (out / "state").exists()
    assert (local / "config" / "bioasq-e4b-c1024-ingest" / "omrs.jsonc").exists()
    assert {p.split("/")[0] for p in _files(out)} == {"bioasq"}


def test_an_index_stage_refuses_index_from(env: Path) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    code = _main(stub, env / "out", *_ingest_args(passages, "--index-from", str(env / "shared")))
    assert code == 2
    assert not (env / "shared").exists()


# --- exit codes and the stage table ------------------------------------------------------


def test_the_stage_table_names_only_the_stages_that_exist() -> None:
    assert set(run_arms.STAGE_TABLE) == set(arms.STAGES)
    assert set(arms.STAGES) == {
        "ingest",
        "seal",
        "search",
        "answer",
        "judge",
        "ragas",
        "closedbook",
        "oracle",
        "determinism",
        "claimkinds",
        "lengthcheck",
    }


@pytest.mark.parametrize(
    ("error", "code"),
    [(RateLimitStop("out of credit; top up"), 5), (None, 6)],
)
def test_a_rate_limit_stop_exits_5_and_open_items_exit_6(
    env: Path, monkeypatch: pytest.MonkeyPatch, error: Any, code: int
) -> None:
    stages35 = load("stages35")

    async def stopped(ctx: Any) -> int:
        raise error or stages35.StageIncomplete("1 file failed")

    monkeypatch.setitem(run_arms.STAGE_TABLE, "ingest", stopped)
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages)) == code
    assert "close" in stub.log


def test_seal_through_the_runner_writes_the_build_environment(env: Path) -> None:
    import lancedb
    import pyarrow as pa

    stub = Stub()
    passages = _prepared(env, stub)
    out = env / "out"
    assert _main(stub, out, *_ingest_args(passages)) == 0
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 2)),
            pa.field("text", pa.string()),
        ]
    )
    table = pa.Table.from_pylist([{"id": "a", "vector": [0.1, 0.2], "text": "t"}], schema=schema)
    lancedb.connect(str(out / "stores" / "e4b-c1024" / "lancedb")).create_table(
        "exp35_bioasq_e4b_c1024", data=table
    )
    seal = ("--dataset", "bioasq", "--index", "e4b-c1024", "--stage", "seal")
    assert _main(stub, out, *seal) == 0
    record = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    assert record == {
        "gpu": "G",
        "image": MACHINE["image"],
        "llama_cpp_build": 11941,
        "gguf_sha256": {"f.gguf": "a" * 64},
    }
    fingerprint = json.loads((out / "bioasq" / "e4b-c1024" / "index-fingerprint.json").read_text())
    assert (fingerprint["chunks"], fingerprint["embedding_dimension"]) == (1, 2)
