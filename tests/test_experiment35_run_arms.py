"""Experiment 35 arm runner CLI (``run_arms.py``) with stub router, guard, engine and judges.

Rules under test: ``--dry-run`` writes and loads the scratch settings and starts
nothing; a wrong GGUF hash stops before any stage file; ``--resume`` skips a
finished stage before the router starts; reranker and hybrid arms search the
baseline index and never ingest; a smoke run (``--limit``) never writes the
experiment's run record; ``--arm all`` runs every arm in table order.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.preflight import PreflightError
from tests._exp35_fixtures import fake_plan, load, make_data_root, make_gguf

from omrs.core.answer.judges.base import JudgeCall, Judgement

arms = load("arms")
outputs35 = load("outputs35")
live35 = load("live35")
run_arms = load("run_arms")


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Path]:
    """Point the runner at tmp data and GGUF folders; restore the environment after."""
    saved = dict(os.environ)
    os.environ["EXP35_DATA_DIR"] = str(make_data_root(tmp_path / "DATA"))
    os.environ["SWEEP_GGUF_DIR"] = str(make_gguf(tmp_path / "gguf"))
    # The conftest provider defaults would override the scratch file (the runner stops on that).
    for name in (
        "EMBED_PROVIDER",
        "LOCAL_BACKEND",
        "EMBEDDING__TOKENIZER_MODEL",
        "EMBEDDING__TOKENIZER_REVISION",
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
        self.log.append(f"ingest {Path(path).name} -> {collection_name}")
        return {"status": "success", "chunks_created": 1}

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.log.append(f"search {kwargs}")
        return [{"chunk_id": "c1", "source": "/c/1001.txt", "score": 0.5}]

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.log.append(f"answer {kwargs}")
        return {
            "status": "grounded",
            "answer": "A claim [1].",
            "citations": [{"ordinal": 1}],
            "evidence": [{"ordinal": 1, "text": "e", "chunk_id": "c1", "source": "/c/1.txt"}],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

    def redact(self, text: str) -> str:
        return text

    def close(self) -> None:
        self.log.append("close")


class _Judge:
    version = "v/1"

    def __init__(self, name: str) -> None:
        self.name = name

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        call = JudgeCall(self.name, "m", None, "b" * 64, self.version, {})
        return Judgement("supported", call)


class Stub:
    """Records every call to the outside world; can refuse the guard."""

    def __init__(self, *, guard_error: str = "") -> None:
        self.log: list[str] = []
        self.guard_error = guard_error

    def plan(self) -> dict[str, Any]:
        return fake_plan()

    def verify_inputs(self, root: Path, dataset: str, files: Sequence[Path]) -> None:
        self.log.append(f"verify_inputs {dataset}")

    def chunking_token_aware(self, settings: Any) -> bool:
        return bool(settings.embedding.tokenizer_model)

    def start_router(self, files: Sequence[str], plan: Any) -> None:
        self.log.append(f"start_router {list(files)}")

    def guard(self, block: Any, *, base_url: str, smoke: bool, runtime_path: Path) -> None:
        self.log.append(f"guard {[m['file'] for m in block['models']]} smoke={smoke}")
        if self.guard_error:
            raise PreflightError(self.guard_error)

    def engine(self) -> _Engine:
        self.log.append("engine")
        return _Engine(self.log)

    def judge(self, name: str, settings: Any, plan: Any) -> _Judge:
        self.log.append(f"judge {name}")
        return _Judge(name)

    def spawn(self, argv: Sequence[str]) -> int:
        self.log.append("spawn " + " ".join(argv))
        return 0


def _main(stub: Stub, out: Path, *args: str) -> int:
    return run_arms.main([*args, "--out-dir", str(out)], deps=stub)


def _files(out: Path) -> set[str]:
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


# --- dry run -----------------------------------------------------------------------------


def test_dry_run_writes_and_loads_the_settings_and_starts_nothing(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = Stub()
    out = env / "out"
    os.environ["OPENROUTER_API_KEY"] = "sentinel-value-0451"
    code = _main(
        stub,
        out,
        "--dataset",
        "bioasq",
        "--arm",
        "hybrid",
        "--stage",
        "answer",
        "--judges",
        "clef_flash,granite_guardian,chat",
        "--answer-host",
        "deepinfra/fp8",
        "--limit",
        "5",
        "--dry-run",
    )
    assert code == 0
    assert stub.log == []
    assert _files(out) == {"config/bioasq-hybrid-answer/omrs.jsonc"}
    printed = capsys.readouterr().out
    plan = json.loads(printed[printed.index("{") :])
    assert plan["nothing_started"] is True
    assert plan["collection"] == "exp35_bioasq_documents_profile_4b"
    assert plan["search"] == {"rerank": True, "hybrid": True}
    assert plan["models"] == ["embedding-baseline-4b", "judge-clef-flash", "judge-granite-guardian"]
    assert len(plan["questions"]) == 5
    assert plan["resolved"]["answer_allowed_hosts"] == "deepinfra/fp8"
    assert "env://" not in printed
    assert "sentinel-value-0451" not in printed
    assert plan["keys_set"] == {"OPENROUTER_API_KEY": True, "OMRS_EXP35_ZAI_KEY": False}


def test_dry_run_of_chunking_off_resolves_the_empty_tokenizer(
    env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _main(
        Stub(),
        env / "out",
        "--dataset",
        "freshstack",
        "--arm",
        "chunking-off",
        "--stage",
        "ingest",
        "--limit",
        "2",
        "--dry-run",
    )
    assert code == 0
    printed = capsys.readouterr().out
    plan = json.loads(printed[printed.index("{") :])
    assert plan["resolved"]["tokenizer_model"] == ""
    assert plan["token_aware"] is False


# --- the guard ---------------------------------------------------------------------------


def test_a_wrong_gguf_hash_stops_before_any_stage_file_or_engine(env: Path) -> None:
    stub = Stub(guard_error="the SHA-256 of Qwen3-Embedding-4B-Q8_0.gguf differs from the plan")
    out = env / "out"
    code = _main(
        stub,
        out,
        "--dataset",
        "bioasq",
        "--arm",
        arms.BASELINE,
        "--stage",
        "ingest",
        "--limit",
        "2",
    )
    assert code == 2
    assert "engine" not in stub.log
    assert not any(name.endswith(".jsonl") for name in _files(out))


def test_every_scored_stage_runs_the_guard_on_the_models_it_loads(env: Path) -> None:
    stub = Stub()
    out = env / "out"
    common = ("--dataset", "bioasq", "--limit", "2")
    assert _main(stub, out, *common, "--arm", "embedding-8b", "--stage", "ingest") == 0
    assert _main(stub, out, *common, "--arm", "embedding-8b", "--stage", "search") == 0
    guards = [line for line in stub.log if line.startswith("guard")]
    assert guards == ["guard ['Qwen3-Embedding-8B-Q8_0.gguf'] smoke=True"] * 2
    assert stub.log.index(guards[0]) < stub.log.index("engine")


def test_smoke_runs_record_the_runtime_in_the_out_dir_and_full_runs_use_guard_run(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def verify(block: Any, *, base_url: str) -> Any:
        calls.append("verify")
        return type("Found", (), {"as_run_record": lambda self: {"build": 1}})()

    def guard_run(folder: Path, block: Any, *, base_url: str, command: str | None) -> Any:
        calls.append("guard_run")
        return verify(block, base_url=base_url)

    path = tmp_path / "runtime.json"
    live35.guard_stage(
        object(), base_url="u", smoke=True, runtime_path=path, verify=verify, guard_run=guard_run
    )
    assert calls == ["verify"]
    assert json.loads(path.read_text()) == {"build": 1}
    live35.guard_stage(
        object(),
        base_url="u",
        smoke=False,
        runtime_path=tmp_path / "x.json",
        verify=verify,
        guard_run=guard_run,
    )
    assert calls == ["verify", "guard_run", "verify"]
    assert not (tmp_path / "x.json").exists()


def test_a_failed_guard_check_writes_no_runtime_file(tmp_path: Path) -> None:
    def verify(block: Any, *, base_url: str) -> Any:
        raise PreflightError("wrong hash")

    path = tmp_path / "runtime.json"
    with pytest.raises(PreflightError):
        live35.guard_stage(
            object(), base_url="u", smoke=True, runtime_path=path, verify=verify, guard_run=verify
        )
    assert not path.exists()


# --- index sharing and resume ------------------------------------------------------------


def test_reranker_and_hybrid_arms_never_ingest(env: Path) -> None:
    stub = Stub()
    for arm in ("reranker-off", "hybrid"):
        code = _main(stub, env / "out", "--dataset", "bioasq", "--arm", arm, "--stage", "ingest")
        assert code == 0
    assert stub.log == []


def test_search_on_a_shared_index_waits_for_the_baseline_ingest(env: Path) -> None:
    stub = Stub()
    out = env / "out"
    common = ("--dataset", "bioasq", "--limit", "2")
    assert _main(stub, out, *common, "--arm", "hybrid", "--stage", "search") == 2
    assert stub.log == []
    assert _main(stub, out, *common, "--arm", arms.BASELINE, "--stage", "ingest") == 0
    assert _main(stub, out, *common, "--arm", "hybrid", "--stage", "search") == 0
    searches = [line for line in stub.log if line.startswith("search")]
    assert (
        searches
        == [
            "search {'top_k': 10, 'collection_name': 'exp35_bioasq_documents_profile_4b', "
            "'rerank': True, 'hybrid': True}"
        ]
        * 2
    )


def test_resume_skips_a_finished_stage_before_the_router_starts(env: Path) -> None:
    out = env / "out"
    args = ("--dataset", "bioasq", "--arm", arms.BASELINE, "--stage", "ingest", "--limit", "2")
    assert _main(Stub(), out, *args) == 0
    again = Stub()
    assert _main(again, out, *args, "--resume") == 0
    assert again.log == []


def test_a_second_run_without_resume_is_refused(env: Path) -> None:
    out = env / "out"
    args = ("--dataset", "bioasq", "--arm", arms.BASELINE, "--stage", "ingest", "--limit", "2")
    assert _main(Stub(), out, *args) == 0
    assert _main(Stub(), out, *args) == 2


# --- answers and judges ------------------------------------------------------------------


def test_answer_stage_without_the_key_variables_stops_before_the_router(env: Path) -> None:
    stub = Stub()
    out = env / "out"
    common = ("--dataset", "bioasq", "--limit", "2", "--arm", arms.BASELINE)
    assert _main(stub, out, *common, "--stage", "ingest") == 0
    stub.log.clear()
    code = _main(
        stub,
        out,
        *common,
        "--stage",
        "answer",
        "--answer-host",
        "deepinfra/fp8",
        "--judges",
        "chat",
    )
    assert code == 2
    assert stub.log == []


def test_answer_stage_runs_every_judge_in_order_on_every_answer(env: Path) -> None:
    stub = Stub()
    out = env / "out"
    common = ("--dataset", "bioasq", "--limit", "2", "--arm", arms.BASELINE)
    assert _main(stub, out, *common, "--stage", "ingest") == 0
    os.environ["OPENROUTER_API_KEY"] = "test-value-not-a-key"
    os.environ["OMRS_EXP35_ZAI_KEY"] = "test-value-not-a-key"
    code = _main(
        stub,
        out,
        *common,
        "--stage",
        "answer",
        "--answer-host",
        "deepinfra/fp8",
        "--judges",
        "clef_flash,granite_guardian,chat",
    )
    assert code == 0
    judges = [line for line in stub.log if line.startswith("judge")]
    assert judges == ["judge clef_flash", "judge granite_guardian", "judge chat"]
    run_dir = outputs35.Layout(out).run_dir("bioasq", arms.BASELINE, 1)
    for name in ("clef_flash", "granite_guardian", "chat"):
        rows = outputs35.read_rows(run_dir / f"judge-{name}.jsonl")
        assert [len(r["verdicts"]) for r in rows] == [1, 1]
    trace = outputs35.read_rows(run_dir / "traces.jsonl")
    assert {row["stage"] for row in trace} == {
        "answer",
        "judge-clef_flash",
        "judge-granite_guardian",
        "judge-chat",
    }
    assert trace[0]["effective_settings"]["arm"] == arms.BASELINE


def test_answer_stage_needs_an_answer_host(env: Path) -> None:
    code = _main(
        Stub(),
        env / "out",
        "--dataset",
        "bioasq",
        "--arm",
        arms.BASELINE,
        "--stage",
        "answer",
        "--dry-run",
    )
    assert code == 2


# --- every arm ---------------------------------------------------------------------------


def test_arm_all_runs_each_arm_in_table_order_in_its_own_process(env: Path) -> None:
    stub = Stub()
    code = run_arms.main(
        [
            "--dataset",
            "freshstack",
            "--arm",
            "all",
            "--stage",
            "search",
            "--limit",
            "5",
            "--resume",
        ],
        deps=stub,
    )
    assert code == 0
    spawned = [line.split("--arm ")[1].split()[0] for line in stub.log]
    assert spawned == list(arms.ARMS)


def test_arm_all_stops_at_the_first_failed_arm(env: Path) -> None:
    stub = Stub()
    stub.spawn = lambda argv: (stub.log.append(" ".join(argv)), 2)[1]  # type: ignore[method-assign]
    code = run_arms.main(["--dataset", "bioasq", "--arm", "all", "--stage", "ingest"], deps=stub)
    assert code == 2
    assert len(stub.log) == 1
