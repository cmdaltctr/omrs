"""B3's stages and tools wired into the Experiment 35 runner (integration F3).

Rules under test: ``determinism`` (G1), ``claimkinds`` and ``lengthcheck``
are runner stages (``arms.STAGE_KINDS``, ``run_arms.STAGE_TABLE``, the
``--stage`` choices); ``--classify-examples`` is on the runner parser;
``determinism`` reads saved files only (no settings, router, guard, engine or
machine record); ``claimkinds`` writes into the answer run folder and loads
no reranker; ``lengthcheck`` writes into ``<out>/lengthcheck`` and refuses
without both checkers; a locked half B and a reader with no run files exit 2;
the join, rebuild, score and cross-table tools keep their own ``--help``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests._exp35_fixtures import load
from tests.test_experiment35_run_arms import env as env  # noqa: F401 - the shared fixture
from tests.test_experiment35_run_stages import RERANK, RunStub, _run, _sealed

arms = load("arms")
cli35 = load("cli35")
lengthcheck35 = load("lengthcheck35")
outputs35 = load("outputs35")
run_arms = load("run_arms")
scoring35 = load("scoring35")
stages35 = load("stages35")

NEW = ("determinism", "claimkinds", "lengthcheck")
ANSWER = "e4b-c1024-r4b-hon"


def _capture(monkeypatch: pytest.MonkeyPatch, stage: str) -> list[Any]:
    seen: list[Any] = []

    async def capture(ctx: Any) -> int:
        seen.append(ctx)
        return 0

    monkeypatch.setitem(run_arms.STAGE_TABLE, stage, capture)
    return seen


def test_the_new_stages_are_in_the_stage_table_and_on_the_parser() -> None:
    assert set(NEW) <= set(run_arms.STAGE_TABLE) == set(arms.STAGES)
    for stage in NEW:
        args = cli35.parse_args(["--dataset", "bioasq", "--setup", ANSWER, "--stage", stage])
        assert args.stage == stage
    args = cli35.parse_args(
        ["--dataset", "bioasq", "--setup", ANSWER, "--stage", "claimkinds"]
        + ["--classify-examples", "ex.json", "--classify-concurrency", "3"]
    )
    assert args.classify_examples == Path("ex.json") and args.classify_concurrency == 3


def test_runner_help_names_the_new_stages(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_arms.main(["--help"])
    assert caught.value.code == 0
    text = capsys.readouterr().out
    for word in (*NEW, "--classify-examples", "--classify-concurrency"):
        assert word in text


@pytest.mark.parametrize("tool", ["join35", "rebuild35", "score35", "crosstable35"])
def test_each_tool_keeps_its_own_help(tool: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        load(tool).main(["--help"])
    assert caught.value.code == 0
    assert "--out-dir" in capsys.readouterr().out


def test_determinism_reads_saved_files_only(env: Path, monkeypatch) -> None:
    seen = _capture(monkeypatch, "determinism")
    stub = RunStub()
    out = env / "out"
    assert _run(stub, out, "--setup", ANSWER, "--stage", "determinism") == 0
    (ctx,) = seen
    assert ctx.layout.root == out.absolute() and ctx.setup == ANSWER
    assert sorted(q.qid for q in ctx.questions) == ["100", "101"]
    assert stub.log == []  # no router, guard, engine or machine
    assert not out.exists() or not any(out.rglob("machine.jsonl"))


def test_determinism_without_its_saved_lists_exits_2_before_any_call(env: Path) -> None:
    stub = RunStub()
    assert _run(stub, env / "out", "--setup", ANSWER, "--stage", "determinism") == 2
    assert stub.log == []


def test_claimkinds_writes_into_the_answer_run_and_loads_no_reranker(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen = _capture(monkeypatch, "claimkinds")
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    assert _run(stub, out, "--setup", RERANK, "--stage", "claimkinds", "--prefreeze") == 0
    (ctx,) = seen
    assert ctx.run_dir == out / "bioasq" / "answer" / RERANK / "run1"
    assert "start_router ['Qwen3-Embedding-4B-Q8_0.gguf']" in stub.log


def test_claimkinds_needs_the_openrouter_key(env: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _capture(monkeypatch, "claimkinds")
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    assert _run(stub, out, "--setup", RERANK, "--stage", "claimkinds", "--prefreeze") == 2


def test_lengthcheck_writes_into_its_own_folder(env: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMRS_EXP35_ZAI_KEY", "test-key")
    seen = _capture(monkeypatch, "lengthcheck")
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    args = ("--setup", RERANK, "--stage", "lengthcheck", "--judges", "chat,clef_flash")
    assert _run(stub, out, *args) == 0
    (ctx,) = seen
    assert ctx.folder == out / "lengthcheck"
    assert (out / "lengthcheck" / "machine.jsonl").exists()
    assert not (out / "bioasq" / "answer").exists()
    assert callable(ctx.judge)


def test_lengthcheck_refuses_without_both_checkers(tmp_path: Path) -> None:
    ctx = SimpleNamespace(layout=outputs35.Layout(tmp_path), args=SimpleNamespace(judges="chat"))
    with pytest.raises(stages35.StageOrderError, match="clef_flash"):
        asyncio.run(lengthcheck35.lengthcheck_stage(ctx))


@pytest.mark.parametrize(
    "error", [scoring35.HalfBLocked("half B is locked"), outputs35.NoRunFiles("no answer.jsonl")]
)
def test_a_locked_half_b_or_missing_run_files_exit_2(
    env: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    async def refuse(ctx: Any) -> int:
        raise error

    monkeypatch.setitem(run_arms.STAGE_TABLE, "judge", refuse)
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    assert _run(stub, out, "--setup", RERANK, "--stage", "judge", "--judges", "clef_flash") == 2


def test_lengthcheck_with_setup_all_runs_once(env: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMRS_EXP35_ZAI_KEY", "test-key")
    seen = _capture(monkeypatch, "lengthcheck")
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    args = ("--setup", "all", "--stage", "lengthcheck", "--judges", "chat,clef_flash")
    assert _run(stub, out, *args) == 0
    assert len(seen) == 1 and not any(line.startswith("spawn") for line in stub.log)
