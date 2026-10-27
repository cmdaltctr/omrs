"""``record_run_start`` passes the found runtime on (reproducible-experiment-runtime, task 3.3)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from experiments._lib.run_record import record_run_start

_SHA = "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _git(tmp_path, "init", "-q")
    path = tmp_path / "experiments" / "44-embed-2026-10-27"
    path.mkdir(parents=True)
    (path / "plan.json").write_text('{"hypothesis": "x"}\n', encoding="utf-8")
    (tmp_path / ".gitignore").write_text("output/\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "--no-verify", "-m", "start")
    return path


def _line(folder: Path) -> dict[str, object]:
    text = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8")
    (line,) = text.splitlines()
    loaded: dict[str, object] = json.loads(line)
    return loaded


def test_runtime_is_written_to_the_run_record(folder: Path) -> None:
    runtime = {"build": 11671, "models": [{"file": "a.gguf", "sha256": _SHA}]}
    record = record_run_start(folder, command="run", runtime=runtime)
    assert record.runtime is not None
    assert record.runtime.build == 11671
    assert _line(folder)["runtime"] == runtime


def test_without_runtime_the_line_has_no_runtime_key(folder: Path) -> None:
    record_run_start(folder, command="run")
    assert "runtime" not in _line(folder)
