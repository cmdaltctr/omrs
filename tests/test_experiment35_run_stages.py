"""The search, answer, judge and Ragas stages through the runner (``run_arms.main``).

Stub router, guard and engine from ``test_experiment35_run_arms.py``. Rules
under test: a reranker-on search loads the embedder and the reranker once
each before the first query and records both in the trace (task 13.7);
``--index-from`` writes nothing under the index folder (task 5.2); exit code
5 for an answer stage that stays rate-limited (task 4.3); ``--answers`` points
the judge and Ragas stages at another answer folder; the wiring of the Ragas
stage (``ctx.router``, ``ctx.runtime_check``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import FakeTokens, load, seal_fixture
from tests.test_experiment35_run_arms import MACHINE, Stub, _files
from tests.test_experiment35_run_arms import env as env  # noqa: F401 - the shared fixture

arms = load("arms")
outputs35 = load("outputs35")
run_arms = load("run_arms")
stagekit35 = load("stagekit35")
stages35 = load("stages35")

RERANK = "e4b-c1024-r4b-hoff"
QIDS = "100,101"


class _Engine:
    store = None

    def __init__(self, log: list[str], answer: Any = None) -> None:
        self.log = log
        self._answer = answer

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.log.append(f"search {text}")
        return [
            {"chunk_id": f"c{i}", "text": "a b", "score": 1.0, "reranked": True} for i in range(100)
        ]

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.log.append(f"answer {text}")
        return await self._answer()

    def redact(self, text: str) -> str:
        return text

    def close(self) -> None:
        self.log.append("close")


class RunStub(Stub):
    """The runner stub with a searching engine."""

    answer: Any = None

    def engine(self) -> _Engine:
        self.log.append("engine")
        return _Engine(self.log, self.answer)


def _sealed(env: Path, stub: RunStub, out: Path, setup: str = RERANK) -> None:
    from types import SimpleNamespace

    seal_fixture(outputs35.Layout(out), "bioasq", setup)
    found = SimpleNamespace(build=11941, models=[{"file": "f.gguf", "sha256": "a" * 64}])
    outputs35.write_json(out / "environment.json", stages35.environment_record(MACHINE, found))


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stagekit35, "qwen3_tokens", lambda: FakeTokens())
    monkeypatch.setattr(stagekit35, "clock", lambda: 0.0)


def _run(stub: Stub, out: Path, *args: str) -> int:
    return run_arms.main(
        ["--dataset", "bioasq", "--qids", QIDS, "--out-dir", str(out), *args], deps=stub
    )


def test_a_reranker_search_loads_both_models_once_before_the_first_query(env: Path) -> None:
    stub = RunStub()
    out = env / "out"
    _sealed(env, stub, out)
    assert _run(stub, out, "--setup", RERANK, "--stage", "search") == 0
    starts = [line for line in stub.log if line.startswith("start_router")]
    assert starts == [
        "start_router ['Qwen3-Embedding-4B-Q8_0.gguf', 'Qwen3-Reranker-4B-Q8_0.gguf']"
    ]
    first = next(i for i, line in enumerate(stub.log) if line.startswith("search"))
    assert stub.log.index(starts[0]) < stub.log.index("engine") < first
    folder = out / "bioasq" / "search" / RERANK / "run1"
    trace = json.loads((folder / "traces.jsonl").read_text().splitlines()[0])
    assert set(trace["model_identities"]) >= {"embedding-baseline-4b", "reranker-4b"}
    assert len((folder / "search.jsonl").read_text().splitlines()) == 2


def test_index_from_writes_nothing_under_the_index_folder(env: Path) -> None:
    stub = RunStub()
    index = env / "index"
    _sealed(env, stub, index)
    (index / "bioasq" / "rebuild.json").unlink()
    before = {p: p.stat().st_mtime_ns for p in index.rglob("*") if p.is_file()}
    out = env / "out"
    args = ("--setup", RERANK, "--stage", "search", "--index-from", str(index))
    assert _run(stub, out, *args) == 0
    after = {p: p.stat().st_mtime_ns for p in index.rglob("*") if p.is_file()}
    assert after == before
    assert "bioasq/search/e4b-c1024-r4b-hoff/run1/search.jsonl" in _files(out)


def test_an_answer_stage_that_stays_rate_limited_exits_5(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    stub = RunStub()

    async def limited() -> dict[str, Any]:
        return {
            "status": "error",
            "answer": None,
            "rate_limited": {"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 0.0},
        }

    stub.answer = limited
    out = env / "out"
    _sealed(env, stub, out)
    args = ("--setup", RERANK, "--stage", "answer", "--rate-limit-attempts", "2")
    assert _run(stub, out, *args) == 5
    folder = out / "bioasq" / "answer" / RERANK / "run1"
    assert not (folder / ".done-answer.json").exists()
    assert "close" in stub.log


@pytest.mark.parametrize("stage", ["judge", "ragas"])
def test_answers_points_the_judge_and_ragas_stages_at_another_folder(
    env: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    seen: list[Any] = []

    async def capture(ctx: Any) -> int:
        seen.append(ctx)
        return 0

    monkeypatch.setitem(run_arms.STAGE_TABLE, stage, capture)
    stub = RunStub()
    stub.router = lambda entry: entry  # type: ignore[attr-defined]
    stub.runtime_check = lambda entry, url: {}  # type: ignore[attr-defined]
    out = env / "out"
    _sealed(env, stub, out)
    args = ("--setup", RERANK, "--stage", stage, "--answers", "oracle", "--prefreeze")
    assert _run(stub, out, *args) == 0
    (ctx,) = seen
    assert ctx.run_dir == out / "bioasq" / "oracle" / RERANK / "run1"
    assert ctx.router is stub.router and ctx.runtime_check is stub.runtime_check
    assert callable(ctx.judge)
    if stage == "ragas":
        assert stub.log[1] == "start_router ['Qwen3-Embedding-4B-Q8_0.gguf']"


def test_the_ragas_stage_options_are_on_the_runner_parser() -> None:
    cli35 = load("cli35")
    args = cli35.parse_args(
        ["--dataset", "bioasq", "--setup", RERANK, "--stage", "ragas", "--ragas-host", "h"]
    )
    assert args.ragas_host == "h" and args.ragas_concurrency == 16 and args.answers == "answer"
