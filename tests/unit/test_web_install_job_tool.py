"""The install job runs the marimo tool action (install-marimo-from-integrations, task 3.1).

A fake executable script in ``tmp_path`` stands in for ``uv``. It records each
run, its arguments and its environment. No test reaches the network or
installs a package.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from omrs.transports.api.install_job import (  # noqa: E402
    MAX_OUTPUT_LINES,
    InstallJob,
    InstallRunning,
)

KEY = "sk-tool-0123456789abcdefghij"  # gitleaks:allow


def fake_uv(tmp_path: Path, body: str = "exit 0") -> str:
    """Write a ``uv`` script that appends each run to ``runs.txt``, then runs *body*."""
    script = tmp_path / "bin" / "uv"
    script.parent.mkdir(parents=True, exist_ok=True)
    out = shlex.quote(str(tmp_path))
    script.write_text(
        f'#!/bin/sh\nprintf "%s|" "$@" >> {out}/runs.txt\necho >> {out}/runs.txt\n'
        f"env > {out}/env.txt\n"
        f'if read line; then echo "stdin: $line"; else echo "stdin closed"; fi\n{body}\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def _runs(tmp_path: Path) -> list[str]:
    path = tmp_path / "runs.txt"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


async def _run_tool(job: InstallJob, argv: list[str], check: bool = True, **kwargs: Any) -> Any:
    job.start_tool("marimo", argv, lambda: check, **kwargs)
    await job.wait()
    return job.snapshot()


async def test_a_tool_job_runs_the_argv_with_no_shell_and_stdin_closed(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path)
    argv = [uv, "tool", "install", "marimo>=0.25.1,<0.26.0", "--with", "jupytext; echo hi"]
    snapshot = await _run_tool(InstallJob(), argv)
    assert _runs(tmp_path) == ["tool|install|marimo>=0.25.1,<0.26.0|--with|jupytext; echo hi|"]
    assert "stdin closed" in snapshot["output"]
    assert snapshot["state"] == "succeeded" and snapshot["reason"] is None


async def test_the_child_environment_has_no_api_key_and_output_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_TOOL_API_KEY", KEY)
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "tools"))
    uv = fake_uv(tmp_path, f"echo leaked {KEY}")
    snapshot = await _run_tool(InstallJob(), [uv, "tool", "install", "marimo"])
    env = (tmp_path / "env.txt").read_text(encoding="utf-8")
    assert "TEST_TOOL_API_KEY" not in env
    assert f"UV_TOOL_DIR={tmp_path / 'tools'}" in env
    assert not any(KEY in line for line in snapshot["output"])


async def test_output_keeps_the_last_forty_lines(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path, "i=0; while [ $i -lt 100 ]; do echo line $i; i=$((i+1)); done")
    snapshot = await _run_tool(InstallJob(), [uv, "tool", "install", "marimo"])
    assert len(snapshot["output"]) == MAX_OUTPUT_LINES
    assert snapshot["output"][-1] == "line 99"


async def test_the_time_limit_ends_with_timed_out(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path, "sleep 5")
    snapshot = await _run_tool(InstallJob(timeout=0.3), [uv, "tool", "install", "marimo"])
    assert snapshot["state"] == "failed" and snapshot["reason"] == "timed-out"


async def test_the_check_function_decides_after_exit_zero(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path)
    job = InstallJob()
    failed = await _run_tool(job, [uv, "tool", "install", "marimo"], check=False)
    assert failed["state"] == "failed" and failed["reason"] == "check-failed"
    assert failed["exit_code"] == 0
    passed = await _run_tool(job, [uv, "tool", "uninstall", "marimo"], action="uninstall")
    assert passed["state"] == "succeeded" and passed["action"] == "uninstall"


async def test_a_non_zero_exit_fails_without_the_check(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path, "exit 3")
    called: list[bool] = []
    job = InstallJob()
    job.start_tool("marimo", [uv, "tool", "install", "marimo"], lambda: called.append(True) or True)
    await job.wait()
    assert job.snapshot()["reason"] == "exit-code" and job.snapshot()["exit_code"] == 3
    assert called == []


async def test_no_uv_pip_check_runs_and_no_restart_is_needed(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path)
    job = InstallJob()
    snapshot = await _run_tool(job, [uv, "tool", "install", "marimo"])
    assert len(_runs(tmp_path)) == 1
    assert job.restart_needed == {}
    assert snapshot["tool"] == "marimo" and snapshot["extra"] is None
    assert snapshot["action"] == "install"


async def test_an_extras_snapshot_has_tool_null(tmp_path: Path) -> None:
    uv = fake_uv(tmp_path)
    job = InstallJob(python="/env/bin/python")
    job.start("anthropic", uv, ["pkg"])
    assert job.snapshot()["tool"] is None and job.snapshot()["extra"] == "anthropic"
    await job.wait()


async def test_a_tool_job_and_an_extras_job_never_run_together(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    uv = fake_uv(tmp_path, f"while [ ! -f {shlex.quote(str(gate))} ]; do sleep 0.02; done")
    job = InstallJob(python="/env/bin/python")
    job.start_tool("marimo", [uv, "tool", "install", "marimo"], lambda: True)
    with pytest.raises(InstallRunning):
        job.start("anthropic", uv, ["pkg"])
    gate.touch()
    await job.wait()
    gate.unlink()
    job.start("anthropic", uv, ["pkg"])
    with pytest.raises(InstallRunning):
        job.start_tool("marimo", [uv, "tool", "install", "marimo"], lambda: True)
    gate.touch()
    await asyncio.wait_for(job.wait(), 10)
