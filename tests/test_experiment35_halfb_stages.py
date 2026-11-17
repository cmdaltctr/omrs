"""Half-B guard on the replicate stages (tasks 16.17, 4; protocol 0.14 item 54).

On a main run the answer, judge, Ragas and claim-kind stages refuse to start
while ``scoring35.require_half_b`` refuses: ``selection.json`` or the OSF
time-stamp record missing, or a time-stamp of another configuration hash.
They refuse before any model call and write nothing. Pre-freeze and smoke runs
write their own folders and skip the guard. Every stage uses the one shared
call, ``stagekit35.require_half_b_open``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests._exp35_fixtures import load

answers35 = load("answers35")
claimstage35 = load("claimstage35")
judges35 = load("judges35")
outputs35 = load("outputs35")
ragas35 = load("ragas35")
scoring35 = load("scoring35")
stagekit35 = load("stagekit35")

SETUP = "e4b-c512-roff-hoff"


class _Called(Exception):
    """A stage went past the guard."""


def _ctx(root: Path, **args: Any) -> Any:
    layout = outputs35.Layout(root)
    run_dir = layout.run_dir("bioasq", "answer", SETUP, 1)
    run_dir.mkdir(parents=True)
    (run_dir / ".done-answer.json").write_text("{}")
    (run_dir / "answer.jsonl").write_text(json.dumps({"qid": "q1", "answer": "a"}) + "\n")
    outputs35.write_json(root / "selection.json", {"embedder": "4b", "reranker": "4b"})
    values = {"prefreeze": False, "smoke": False, "judges": "chat", "rate_limit_attempts": 1}

    def stop(*_: Any, **__: Any) -> Any:
        raise _Called

    return SimpleNamespace(
        layout=layout,
        dataset="bioasq",
        setup=SETUP,
        kind="answer",
        run=1,
        run_dir=run_dir,
        questions=[SimpleNamespace(qid="q1", text="q", reference="r")],
        key={"seed": 1},
        resume=False,
        args=SimpleNamespace(**{**values, **args}),
        judge=stop,
        classifier=stop,
        classifier_version="v1",
        router=stop,
        runtime_check=stop,
        engine=SimpleNamespace(answer=stop),
    )


STAGES = {
    "answer": lambda c: answers35.answer_stage(c),
    "judge": lambda c: judges35.judge_stage(c),
    "ragas": lambda c: ragas35.ragas_stage(c, {}),
    "claimkinds": lambda c: claimstage35.claimkinds_stage(c),
}


@pytest.mark.parametrize("stage", sorted(STAGES))
def test_a_main_run_stage_refuses_while_half_b_is_locked(tmp_path: Path, stage: str) -> None:
    ctx = _ctx(tmp_path)
    before = sorted(p.name for p in ctx.run_dir.iterdir())
    with pytest.raises(scoring35.HalfBLocked, match="osf-timestamp.json"):
        asyncio.run(STAGES[stage](ctx))
    assert sorted(p.name for p in ctx.run_dir.iterdir()) == before


@pytest.mark.parametrize("stage", sorted(STAGES))
def test_a_time_stamp_of_another_selection_is_refused(tmp_path: Path, stage: str) -> None:
    ctx = _ctx(tmp_path)
    selection = {"embedder": "4b", "reranker": "4b", "configuration_hash": "a" * 64}
    outputs35.write_json(tmp_path / "selection.json", selection)
    stamp = {"uploaded_at": "t", "file_sha256": "f" * 64, "configuration_hash": "b" * 64}
    outputs35.write_json(tmp_path / "osf-timestamp.json", stamp)
    with pytest.raises(scoring35.HalfBLocked, match="b" * 64):
        asyncio.run(STAGES[stage](ctx))


@pytest.mark.parametrize("flag", ["prefreeze", "smoke"])
def test_pre_freeze_and_smoke_runs_skip_the_guard(tmp_path: Path, flag: str) -> None:
    ctx = _ctx(tmp_path, **{flag: True})
    stagekit35.require_half_b_open(ctx)  # no files: no refusal
