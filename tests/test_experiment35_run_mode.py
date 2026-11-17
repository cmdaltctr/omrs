"""Experiment 35 runner: the run mode in the stage key and the index check (review R2).

Rules under test: a smoke or pre-freeze run is never accepted as "done earlier"
by a main run (R2-01); every stage that reads an index checks the ingest
done-marker configuration before its first query (R2-05); a ``chat`` claim
failure exits 4 with a message that names the failed call (R2-08).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load
from tests.test_experiment35_run_arms import (  # noqa: F401
    MACHINE,
    Stub,
    _ingest_args,
    _main,
    _prepared,
    env,
)

judges35 = load("judges35")
run_arms = load("run_arms")

ALL_BIOASQ = "100,101,102,103,104,105"


@pytest.mark.parametrize("flags", [("--prefreeze",), ("--qids", ALL_BIOASQ)])
def test_a_main_resume_refuses_a_stage_another_run_mode_wrote_and_names_the_field(
    env: Path,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages, *flags)) == 0
    again = Stub(plan=stub._plan)
    assert _main(again, env / "out", *_ingest_args(passages, "--resume")) == 2
    assert again.log == []
    assert "run_mode" in capsys.readouterr().out


def test_the_ingest_marker_and_the_key_hold_the_run_mode(env: Path) -> None:  # noqa: F811
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages, "--prefreeze")) == 0
    folder = env / "out" / "bioasq" / "e4b-c1024"
    marker = json.loads((folder / ".done-ingest.json").read_text(encoding="utf-8"))
    key = json.loads((folder / "ingest.key.json").read_text(encoding="utf-8"))
    assert marker["config"]["run_mode"] == key["run_mode"] == "prefreeze"


def _sealed(out: Path) -> None:
    """Write the build environment record the stub machine and guard give."""
    record = {"gpu": "G", "image": MACHINE["image"], "llama_cpp_build": 11941}
    out.mkdir(parents=True, exist_ok=True)
    (out / "environment.json").write_text(
        json.dumps({**record, "gguf_sha256": {"f.gguf": "a" * 64}}), encoding="utf-8"
    )


def _search_key(root: Path, monkeypatch: pytest.MonkeyPatch, *flags: str) -> dict[str, Any]:
    """Run a search command whose stage records its key; return the key."""
    seen: dict[str, Any] = {}
    _sealed(root / "out")

    async def stage(ctx: Any) -> int:
        seen.update(ctx.key)
        return 0

    monkeypatch.setitem(run_arms.STAGE_TABLE, "search", stage)
    args = ("--dataset", "bioasq", "--setup", "e4b-c1024-r4b-hoff", "--stage", "search", *flags)
    assert _main(Stub(), root / "out", *args) == 0
    return seen


def test_a_search_key_expects_the_index_configuration_of_the_ingest(
    env: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = Stub()
    passages = _prepared(env, stub)
    assert _main(stub, env / "out", *_ingest_args(passages)) == 0
    marker = json.loads((env / "out" / "bioasq" / "e4b-c1024" / ".done-ingest.json").read_text())
    key = _search_key(env, monkeypatch)
    assert key["index_config"] == marker["config"]
    assert key["settings_sha256"] != marker["config"]["settings_sha256"]


def test_a_smoke_search_key_does_not_ask_for_the_index_run_mode(
    env: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _search_key(env, monkeypatch, "--qids", "100")
    assert key["run_mode"] == "smoke" and "run_mode" not in key["index_config"]


def test_a_chat_claim_failure_exits_4_and_names_the_call(
    env: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def stage(ctx: Any) -> int:
        raise judges35.ClaimCallStop("q7", 2, "RuntimeError: judge timeout")

    monkeypatch.setitem(run_arms.STAGE_TABLE, "judge", stage)
    monkeypatch.setenv(load("arms").GLM_KEY_ENV, "test-value")
    _sealed(env / "out")
    args = ("--dataset", "bioasq", "--setup", "e4b-c1024-r4b-hoff", "--stage", "judge")
    assert _main(Stub(), env / "out", *args, "--judges", "chat") == 4
    out = capsys.readouterr().out
    assert "cannot start" not in out
    assert "q7" in out and "claim 2" in out and "--resume" in out
