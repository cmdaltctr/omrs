"""Experiment 35 run guard: unfrozen plan, dirty tree and server arguments (tasks 5.7, 5.8).

``guard_run`` (``experiments/_lib/run_guard.py``) refuses a main stage while
``plan.json`` ``frozen`` is empty or the tree is dirty; a pre-freeze run needs
its own folder. ``verify_llamacpp_runtime(..., check_args=True)`` compares the
planned ``server_args`` with the router's ``status.args``. The router reply is
injected in place of the HTTP read; a temporary git repository gives the guard
a commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from experiments._lib import llamacpp_runtime
from experiments._lib.llamacpp_runtime import verify_llamacpp_runtime
from experiments._lib.preflight import PreflightError
from experiments._lib.run_guard import guard_run

from omrs.core.experiment_records.runtime_block import RuntimeBlock

FILE = "Clef-Flash-Q8_0.gguf"
BUILD = 11941
WEIGHTS = b"gguf weights"
PLANNED = {
    "ctx-size": 32768,
    "parallel": 1,
    "flash-attn": True,
    "n-gpu-layers": "all",
    "fit": False,
    "cache-prompt": False,
    "spec-type": "none",
}
# What the router lists for that preset (b11941 spelling, as in the router spike evidence).
ROUTER_ARGS = [
    "llama-server", "--host", "127.0.0.1", "--port", "0", "--alias", "clef",
    "--ctx-size", "32768", "--parallel", "1", "--flash-attn", "on",
    "--n-gpu-layers", "all", "--fit", "off",
]  # fmt: skip


def _block(server_args: dict[str, Any]) -> RuntimeBlock:
    return RuntimeBlock.model_validate(
        {
            "models": [
                {
                    "role": "judge-clef-flash",
                    "repository": "ggml-org/Clef-Flash-GGUF",
                    "file": FILE,
                    "sha256": hashlib.sha256(WEIGHTS).hexdigest(),
                    "runtime": "llama.cpp",
                    "build": BUILD,
                    "server_args": server_args,
                }
            ],
            "tolerance": [{"metric": "faithfulness", "max_abs_change": 0.01}],
        }
    )


@pytest.fixture
def router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Inject the router's ``/props`` and ``/v1/models`` replies; count the reads."""
    weights = tmp_path / "weights" / FILE
    weights.parent.mkdir()
    weights.write_bytes(WEIGHTS)
    state: dict[str, Any] = {"args": [*ROUTER_ARGS, "--model", str(weights)], "reads": []}

    def reply(base_url: str, path: str) -> Any:
        state["reads"].append(path)
        if path == "/props":
            return {"role": "router", "model_path": "none", "build_info": f"b{BUILD}-abc"}
        return {"data": [{"id": "clef", "status": {"value": "loaded", "args": state["args"]}}]}

    monkeypatch.setattr(llamacpp_runtime, "_get_json", reply)
    return state


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed experiment folder with a frozen plan and a pre-registration."""
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "repo"
    path = repo / "experiments" / "35-full-rag-benchmark-2026-11-01"
    path.mkdir(parents=True)
    _git(repo, "init", "-q")
    frozen = [{"item": "preregistration.md", "sha256": "a" * 64}]
    (path / "plan.json").write_text(json.dumps({"frozen": frozen}) + "\n", encoding="utf-8")
    (path / "preregistration.md").write_text("# Pre-registration\n", encoding="utf-8")
    (repo / ".gitignore").write_text("output/\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--no-verify", "-m", "start")
    return path


def _unfreeze(folder: Path) -> None:
    (folder / "plan.json").write_text('{"frozen": []}\n', encoding="utf-8")
    _git(folder.parents[1], "commit", "-q", "--no-verify", "-am", "unfreeze")


def _records(folder: Path) -> Path:
    return folder / "output" / "run-records.jsonl"


# --- 5.7 unfrozen plan and dirty tree --------------------------------------------------


def test_main_stage_refuses_an_unfrozen_plan_before_any_call(
    folder: Path, router: dict[str, Any]
) -> None:
    _unfreeze(folder)
    with pytest.raises(PreflightError, match="frozen"):
        guard_run(folder, _block({}), base_url="http://127.0.0.1:9", command="run")
    assert router["reads"] == []
    assert not _records(folder).exists()


def test_main_stage_refuses_a_dirty_tree(folder: Path, router: dict[str, Any]) -> None:
    (folder / "stages35.py").write_text("# an uncommitted change\n", encoding="utf-8")
    with pytest.raises(PreflightError, match="git_dirty"):
        guard_run(folder, _block({}), base_url="http://127.0.0.1:9", command="run")
    assert router["reads"] == []
    assert not _records(folder).exists()


def test_clean_frozen_main_stage_passes_and_records(folder: Path, router: dict[str, Any]) -> None:
    guard_run(folder, _block({}), base_url="http://127.0.0.1:9", command="run")
    (line,) = _records(folder).read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["git_dirty"] is False


def test_prefreeze_run_passes_and_writes_its_record_to_its_own_folder(
    folder: Path, router: dict[str, Any], tmp_path: Path
) -> None:
    _unfreeze(folder)
    (folder / "stages35.py").write_text("# an uncommitted change\n", encoding="utf-8")
    own = tmp_path / "prefreeze-out"
    guard_run(folder, _block({}), base_url="http://127.0.0.1:9", command="run", prefreeze_dir=own)
    assert not _records(folder).exists()
    (line,) = (own / "run-records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["git_dirty"] is True
    assert record["command"] == "run"
    assert record["runtime"]["build"] == BUILD
    expected = hashlib.sha256((folder / "preregistration.md").read_bytes()).hexdigest()
    assert record["preregistration_sha256"] == expected


# --- 5.8 server-argument check ---------------------------------------------------------


def test_matching_server_args_pass_with_the_check_on(router: dict[str, Any]) -> None:
    found = verify_llamacpp_runtime(_block(PLANNED), base_url="http://127.0.0.1:9", check_args=True)
    assert found.models[0]["file"] == FILE


def test_differing_server_arg_raises_and_names_file_and_argument(router: dict[str, Any]) -> None:
    planned = {**PLANNED, "ctx-size": 8192, "cache-prompt": True}
    with pytest.raises(PreflightError, match=FILE) as caught:
        verify_llamacpp_runtime(_block(planned), base_url="http://127.0.0.1:9", check_args=True)
    message = str(caught.value)
    assert "ctx-size" in message and "cache-prompt" in message
    assert "parallel" not in message


def test_default_check_is_unchanged_for_other_experiments(router: dict[str, Any]) -> None:
    planned = {**PLANNED, "ctx-size": 8192}
    found = verify_llamacpp_runtime(_block(planned), base_url="http://127.0.0.1:9")
    assert found.build == BUILD


def test_guard_run_passes_check_args_through(folder: Path, router: dict[str, Any]) -> None:
    block = _block({**PLANNED, "ctx-size": 8192})
    guard_run(folder, block, base_url="http://127.0.0.1:9", command="run")
    with pytest.raises(PreflightError, match="ctx-size"):
        guard_run(folder, block, base_url="http://127.0.0.1:9", command="run", check_args=True)
